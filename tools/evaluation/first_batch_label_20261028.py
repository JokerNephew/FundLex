#!/usr/bin/env python3
"""Independent, versioned labels for the 2026-10-28 first batch.

This tool is deliberately independent from the recall engine:

* it reads only the frozen selection, the guide DOCX, the guide rule map
  (for rule ids/templates), and the original contract DOCX files;
* it never reads engine reports, final/redline artifacts, engine prompts or
  historical P6 labels;
* labels are produced by a real model outside the engine model family
  (default: gemini-4-argon) and reviewed by a second model family
  (default: kimi-k3.1-pro).

Provider credentials are read at run time from the protected deployment env
file and are never written to the output or logs.

Usage:
    .venv/bin/python tools/evaluation/first_batch_label_20261028.py --case B02
    .venv/bin/python tools/evaluation/first_batch_label_20261028.py --all
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import docx
import httpx

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SELECTION = ROOT / "docs/evidence/selection-first-batch-20261028.json"
DEFAULT_GUIDE = ROOT / "references/source/v4存量基金适用销售费用新规的基金合同修改指引_文案勘误版.docx"
DEFAULT_RULES = ROOT / "guides/builtin_guide_v1.json"
DEFAULT_OUT = ROOT / "var/recall-first-evaluation/first-batch-20261028/labels-first-batch-20261028.json"
PROTECTED_ENV_CANDIDATES = [
    os.environ.get("FUNDLEX_MODEL_ENV", ""),
    "/tmp/opencode/comprehensive-remediation-20261028/model-new.env",
    "/etc/fundlex-recall.env",
]

RULE_IDS = [f"G{i:02d}" for i in range(1, 23)]
RULE_TITLES = {
    "G01": "释义-基金份额类别定义（追加直销/其他渠道政策）",
    "G02": "释义-基金份额类别定义（按实际收费组替换类别）",
    "G03": "基金的基本情况-份额类别设置（追加直销/其他渠道政策）",
    "G04": "基金的基本情况-份额类别设置（按实际收费组替换类别）",
    "G05": "基金的基本情况-份额类别设置（费率调整机制）",
    "G06": "基金的基本情况-份额类别设置（删除类别间不得转换）",
    "G07": "申购赎回-单一类别申购费率表述",
    "G08": "申购赎回-多类别申购费率表述",
    "G09": "申购赎回-多类别赎回金额计算",
    "G10": "申购赎回-单一类别申购费用承担",
    "G11": "申购赎回-多类别申购费用承担",
    "G12": "申购赎回-赎回费用全额计入基金财产",
    "G13": "申购赎回-删除7日惩罚性赎回费",
    "G14": "申购赎回-促销费率调整表述",
    "G15": "基金费用-删除销售服务费旧支付安排",
    "G16": "基金费用-追加销售服务费新机制",
    "G17": "基金费用-删除销售服务费用途条款",
    "G18": "收益分配-费用差异原因表述",
    "G19": "清算-浮动管理费单类别",
    "G20": "清算-浮动管理费多类别",
    "G21": "清算-非浮动管理费单类别（不做替换）",
    "G22": "清算-非浮动管理费多类别（返还销售服务费）",
}
ALLOWED_OPS = {
    "G01": {"append"},
    "G02": {"replace"},
    "G03": {"append"},
    "G04": {"replace"},
    "G05": {"replace", "delete"},
    "G06": {"delete"},
    "G07": {"replace"},
    "G08": {"replace"},
    "G09": {"replace"},
    "G10": {"replace"},
    "G11": {"replace"},
    "G12": {"replace"},
    "G13": {"delete"},
    "G14": {"replace"},
    "G15": {"delete"},
    "G16": {"append"},
    "G17": {"delete"},
    "G18": {"replace"},
    "G19": {"replace"},
    "G20": {"replace"},
    "G21": set(),
    "G22": {"replace"},
}

STATUS_ALIASES = {
    "target": "target",
    "required": "target",
    "change": "target",
    "needs_change": "target",
    "needschange": "target",
    "edit": "target",
    "satisfied": "satisfied",
    "already_satisfied": "satisfied",
    "alreadysatisfied": "satisfied",
    "pass": "satisfied",
    "not_applicable": "not_applicable",
    "notapplicable": "not_applicable",
    "n/a": "not_applicable",
    "na": "not_applicable",
    "unknown": "unknown",
    "uncertain": "unknown",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def find_span(text: str, quote: str) -> tuple[int, int] | None:
    """Find a quote allowing only whitespace differences; return original span."""
    if not quote:
        return None
    pos = (text or "").find(quote)
    if pos >= 0:
        return pos, pos + len(quote)
    norm_chars: list[str] = []
    index_map: list[int] = []
    for idx, ch in enumerate(text or ""):
        if not ch.isspace():
            norm_chars.append(ch)
            index_map.append(idx)
    needle = compact(quote)
    if not needle:
        return None
    pos = "".join(norm_chars).find(needle)
    if pos < 0:
        return None
    return index_map[pos], index_map[pos + len(needle) - 1] + 1


def compact_offsets(text: str, start: int, end: int) -> tuple[int, int]:
    return len(compact(text[:start])), len(compact(text[:end]))


def clean_json_content(content: str) -> str:
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _read_env_file(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path:
        return values
    try:
        text = Path(path).read_text(encoding="utf-8")
    except Exception:
        try:
            text = subprocess.run(
                ["sudo", "-n", "cat", path], capture_output=True, text=True, check=True, timeout=20
            ).stdout
        except Exception:
            return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_provider_env(explicit_path: str = "") -> tuple[str, str, str]:
    """Load the provider endpoint/key at run time without logging the key."""
    env = dict(os.environ)
    candidates = ([explicit_path] if explicit_path else []) + PROTECTED_ENV_CANDIDATES
    for path in candidates:
        if not path:
            continue
        values = _read_env_file(path)
        if values.get("LLM_BASE_URL") and values.get("LLM_API_KEY"):
            env.update({k: v for k, v in values.items() if v})
            break
    base = env.get("LLM_BASE_URL", "").rstrip("/")
    key = env.get("LLM_API_KEY", "")
    model = env.get("LLM_MODEL", "")
    if not base or not key:
        raise RuntimeError("provider endpoint/key missing; set FUNDLEX_MODEL_ENV or the protected env file")
    return base, key, model


class ModelClient:
    def __init__(self, base_url: str, api_key: str, *, timeout_s: float = 300.0):
        self.base_url = base_url
        self.api_key = api_key
        self.timeout_s = timeout_s
        self.session = os.environ.get("OPENCODE_SESSION_ID", "")
        self.usage: list[dict[str, Any]] = []
        self._usage_lock = threading.Lock()
        self.client = httpx.Client(timeout=httpx.Timeout(timeout_s, connect=30.0))

    def close(self) -> None:
        self.client.close()

    def chat_json(
        self,
        *,
        model: str,
        system: str,
        user: str,
        max_tokens: int,
        phase: str,
        case_id: str,
        retries: int = 3,
        temperature: float = 0.0,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        headers = {
            "Authorization": "Bearer " + self.api_key,
            "Content-Type": "application/json",
            "User-Agent": "fundlex-independent-labeler/1.0",
        }
        if self.session:
            headers["x-opencode-session"] = self.session
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        last_error = ""
        for attempt in range(retries + 1):
            started = time.monotonic()
            try:
                response = self.client.post(
                    self.base_url + "/chat/completions",
                    headers=headers,
                    json=payload,
                )
            except httpx.HTTPError as exc:
                last_error = type(exc).__name__
                if attempt < retries:
                    time.sleep(min(2 ** attempt, 8))
                    continue
                raise RuntimeError(f"model transport error: {last_error}") from None
            latency_ms = round((time.monotonic() - started) * 1000)
            event: dict[str, Any] = {
                "phase": phase,
                "case_id": case_id,
                "model": model,
                "attempt": attempt + 1,
                "http_status": response.status_code,
                "latency_ms": latency_ms,
                "prompt_sha256": sha256_bytes(user.encode("utf-8")),
                "request_id": response.headers.get("x-request-id"),
            }
            if response.status_code == 429 or 500 <= response.status_code <= 599:
                detail = response.text[:200].replace("\n", " ")
                last_error = f"HTTP {response.status_code}"
                retry_after = 0.0
                try:
                    retry_after = float(response.headers.get("retry-after") or 0)
                except ValueError:
                    retry_after = 0.0
                with self._usage_lock:
                    self.usage.append({**event, "error": last_error, "error_detail": detail})
                if attempt < retries:
                    delay = retry_after or min(8 * (2 ** attempt), 120)
                    time.sleep(max(1.0, delay))
                    continue
                raise RuntimeError(f"model provider error: {last_error}: {detail}")
            if response.status_code >= 400:
                detail = response.text[:300].replace("\n", " ")
                if response.status_code == 400 and "temperature" in detail and temperature != 1.0:
                    temperature = 1.0
                    payload["temperature"] = 1.0
                    with self._usage_lock:
                        self.usage.append({**event, "error": "temperature_retry"})
                    continue
                with self._usage_lock:
                    self.usage.append({**event, "error": f"HTTP {response.status_code}", "error_detail": detail})
                raise RuntimeError(f"model provider HTTP {response.status_code}: {detail}")
            try:
                body = response.json()
                choice = body["choices"][0]
                content = choice["message"].get("content")
                if isinstance(content, list):
                    content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
                if not (content or "").strip():
                    reasoning = choice["message"].get("reasoning_content") or choice["message"].get("reasoning") or ""
                    if isinstance(reasoning, list):
                        reasoning = "".join(part.get("text", "") for part in reasoning if isinstance(part, dict))
                    match = re.search(r"\{.*\}", reasoning, re.S)
                    if match:
                        content = match.group(0)
                value = json.loads(clean_json_content(content))
            except Exception:
                with self._usage_lock:
                    self.usage.append({**event, "error": "response_not_json"})
                if attempt < retries:
                    time.sleep(min(2 ** attempt, 8))
                    continue
                raise RuntimeError("model returned invalid JSON") from None
            usage = body.get("usage") or {}
            event.update({
                "actual_model": str(body.get("model") or model),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "finish_reason": choice.get("finish_reason"),
                "response_sha256": sha256_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")),
            })
            with self._usage_lock:
                self.usage.append(event)
            if choice.get("finish_reason") == "length":
                raise RuntimeError("model output truncated")
            if not isinstance(value, dict):
                raise RuntimeError("model output is not a JSON object")
            return value, event
        raise RuntimeError(f"model call failed: {last_error}")


@dataclass
class Para:
    index: int
    text: str
    style: str
    section_path: str
    is_summary: bool
    is_heading: bool


@dataclass
class DocModel:
    path: Path
    paragraphs: list[Para]
    summary_start: int | None
    summary_headings: list[str]
    protection: dict[str, Any]
    text_sha256: str

    def nonempty(self) -> Iterable[Para]:
        return (p for p in self.paragraphs if p.text.strip())


SUB_HEADING_RE = re.compile(r"^(?:[一二三四五六七八九十百]+、|（[一二三四五六七八九十百]+）)")
PART_HEADING_RE = re.compile(r"^第[一二三四五六七八九十百]+部分")


def _heading_like(text: str, style: str) -> bool:
    t = (text or "").strip()
    if not t or len(t) > 70:
        return False
    if style.lower().startswith("heading"):
        return True
    if PART_HEADING_RE.match(t):
        return True
    if re.match(r"^[一二三四五六七八九十百]+、.*摘要", t):
        return True
    if SUB_HEADING_RE.match(t) and "。" not in t and len(t) <= 45:
        return True
    return False


def build_doc_model(path: Path) -> DocModel:
    document = docx.Document(str(path))
    raw = [(p.text or "", p.style.name if p.style is not None else "") for p in document.paragraphs]
    summary_start: int | None = None
    for idx, (text, style) in enumerate(raw):
        t = text.strip()
        if not t or len(t) > 60 or "摘要" not in t:
            continue
        if style.lower().startswith("toc"):
            continue
        if style.lower().startswith("heading") or re.match(r"^(?:第[一二三四五六七八九十百]+部分|[一二三四五六七八九十百]+、)", t):
            summary_start = idx
    paragraphs: list[Para] = []
    part = "封面/目录"
    sub = ""
    summary_headings: list[str] = []
    for idx, (text, style) in enumerate(raw):
        is_summary = summary_start is not None and idx >= summary_start
        heading = _heading_like(text, style)
        if heading:
            t = text.strip()
            if PART_HEADING_RE.match(t) or ("摘要" in t and len(t) <= 60):
                part = t
                sub = ""
                if is_summary:
                    summary_headings.append(t)
            else:
                sub = t
                if is_summary:
                    summary_headings.append(t)
        section = part if not sub else f"{part} > {sub}"
        paragraphs.append(Para(idx, text, style, section, is_summary, heading))
    protection = detect_protection(path)
    text_sha = sha256_bytes("\n".join(p.text for p in paragraphs).encode("utf-8"))
    return DocModel(path, paragraphs, summary_start, summary_headings, protection, text_sha)


def detect_protection(path: Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(path) as archive:
            settings = archive.read("word/settings.xml")
    except (KeyError, OSError, zipfile.BadZipFile):
        return {"protected": False, "edit": None, "enforcement": None}
    match = re.search(rb"<w:documentProtection\b([^>]*)/?>", settings)
    if not match:
        return {"protected": False, "edit": None, "enforcement": None}
    attrs = match.group(1).decode("utf-8", "ignore")
    edit = re.search(r'w:edit="([^"]+)"', attrs)
    enforcement = re.search(r'w:enforcement="([^"]+)"', attrs)
    return {
        "protected": True,
        "edit": edit.group(1) if edit else None,
        "enforcement": enforcement.group(1) if enforcement else None,
        "raw_sha256": sha256_bytes(settings),
        "policy": "DOCUMENT_PROTECTED",
    }


def load_guide(path: Path) -> tuple[list[str], str]:
    document = docx.Document(str(path))
    paragraphs = [(p.text or "").strip() for p in document.paragraphs]
    return paragraphs, sha256_file(path)


def guide_prompt(rules: dict[str, Any], guide_paras: list[str], rule_ids: list[str] | None = None) -> str:
    lines: list[str] = []
    by_id = {g["rule_id"]: g for g in rules["groups"]}
    for rule_id in (rule_ids or RULE_IDS):
        group = by_id[rule_id]
        lines.append(f"### {rule_id} {group.get('title', '')}")
        lines.append("要求：" + (group.get("requirement") or ""))
        for op in group.get("operations") or []:
            lines.append(
                f"- op={op.get('op')} condition={json.dumps(op.get('condition'), ensure_ascii=False)}"
            )
            if op.get("old_text"):
                lines.append("  旧文：" + op["old_text"])
            if op.get("new_text"):
                lines.append("  新文：" + op["new_text"])
        refs = group.get("source_paragraphs") or []
        for ref in refs:
            if isinstance(ref, int) and 0 <= ref < len(guide_paras):
                lines.append(f"  指引原段[{ref}]：" + guide_paras[ref])
        lines.append("")
    return "\n".join(lines)


def contract_prompt(doc: DocModel) -> str:
    lines: list[str] = []
    for para in doc.nonempty():
        marker = "S" if para.is_summary else "M"
        lines.append(f"[p{para.index:04d}][{marker}] §{para.section_path} | {para.text}")
    return "\n".join(lines)


OUTPUT_SCHEMA_TEXT = r"""
输出必须是单个 JSON 对象，字段如下（不要输出 Markdown 代码围栏，不要解释）：

{
  "fund": {
    "name": "基金全称",
    "fund_type": "产品类型，如混合型/债券型/ETF联接/QDII/FOF/LOF/指数型等",
    "fund_type_evidence": {"paragraph_index": 0, "quote": "原文逐字引用"},
    "eligible": true,
    "eligibility_reason": "依据原件说明为何属于本指引适用范围；若不确定写unknown理由",
    "eligibility_evidence": {"paragraph_index": 0, "quote": "原文逐字引用"} 或 null,
    "share_classes": [
      {"label": "A", "pays_purchase_fee": true, "charges_sales_service_fee": false,
       "evidence": {"paragraph_index": 0, "quote": "原文逐字引用"}}
    ],
    "class_count": 2,
    "has_sales_service_fee": true,
    "floating_management_fee": false,
    "floating_fee_evidence": {"paragraph_index": 0, "quote": "原文逐字引用"} 或 null,
    "direct_sales_exemption_present": true,
    "one_year_holding_rule_present": true,
    "payment_mechanism": {"old_arrangement_present": true, "working_days": "5", "evidence": {"paragraph_index": 0, "quote": "原文逐字引用"}}
  },
  "rule_coverage": [
    {"rule_id": "G01", "scope": "main", "status": "target|satisfied|not_applicable|unknown",
     "paragraph_index": 0 或 null, "reason": "简短依据", "evidence_quote": "原文逐字引用" 或 null}
  ],
  "targets": [
    {"rule_id": "G01", "op": "append|replace|delete", "scope": "main|summary",
     "paragraph_index": 0,
     "old_text": "必须逐字来自该段；append时为空字符串",
     "required_text": "替换/追加后的完整文字；delete时为空字符串",
     "source_quote": "原文逐字引用；append时为锚点段落引用",
     "anchor_quote": "append时的锚点逐字引用，否则null",
     "anchor_position": "end_of_paragraph" 或 null,
     "requirement": "该站点具体应完成的业务要求",
     "class_scope": ["A", "C"],
     "guide_paragraphs": [0, 1, 2],
     "rationale": "为何该站点属于本规则且必须修改；范围外不写"}
  ],
  "uncertain": [
    {"rule_id": "G01", "scope": "main", "paragraph_index": 0,
     "issue": "无法确定的点", "candidates": ["候选解释"]}
  ]
}

字段规则：
- `rule_coverage` 必须覆盖 G01–G22 在 main 的每一条；若存在摘要，还要覆盖摘要中实际存在的章节对应的规则。
- 一个规则在一个 scope 有多个站点时，`rule_coverage` 只写一条 status=target，`targets` 写多条。
- `paragraph_index` 是合同 DOCX 的 python-docx 零基段号，必须与 [pNNNN] 一致。
- `old_text`、`source_quote`、`anchor_quote`、事实 quote 必须逐字来自原文，不能省略、改写或用省略号；允许原文字符间空格差异。
- `old_text` 只取真正需要变化的最小连续片段；delete 时取被删除的完整句子/短语，required_text 为空。
- append 时 paragraph_index 是锚点段（追加到该段之后），old_text 为空，anchor_quote 必填，anchor_position=end_of_paragraph。
"""


def system_prompt() -> str:
    return (
        "你是基金合同修订的独立标注专家。你只依据给定的指引和合同原文工作，"
        "不参考任何引擎预测、历史标签或报告。你的任务是逐段通读合同，找出所有"
        "真实应改站点并给出可评分的位置、原文和新文；不确定时必须列入 uncertain，"
        "不得编造。只输出有效 JSON。"
    )


def primary_prompt(doc: DocModel, guide_text: str, rule_ids: list[str] | None = None) -> str:
    rule_note = ""
    if rule_ids:
        rule_note = (
            "\n# 本轮标注范围\n只输出以下规则的 rule_coverage 与 targets："
            + "、".join(rule_ids)
            + "。其他规则不要出现在本轮输出中。\n"
        )
    protection_note = ""
    if doc.protection.get("protected"):
        protection_note = (
            "\n# 文档保护\n"
            f"该 DOCX 的 word/settings.xml 含 documentProtection="
            f"{json.dumps(doc.protection, ensure_ascii=False)}。按 DOCUMENT_PROTECTED 边界处理："
            "targets 必须为空；rule_coverage 全部标 not_applicable，reason 以 DOCUMENT_PROTECTED 开头；"
            "仍须提取事实并写入 uncertain 说明未评估修改。\n"
        )
    return f"""
# 任务
为一份存量基金合同建立独立、可评分的修改标签。请通读下面全部合同段落，依据指引
判断产品事实、每条规则（G01–G22）的适用性，并列出**所有真实应改站点**。不要只看
每规则一个示例站点：正文与摘要分别、同一规则下多个同类段落/多个叶子分别列出。

# 指引规则（G01–G22）
{guide_text}

# 合同原文
编号 pNNNN 为 python-docx 零基段号；[M] 为正文，[S] 为“基金合同内容摘要”部分。
§ 后为该段所在章节路径。
{contract_prompt(doc)}
{protection_note}{rule_note}
# 输出 JSON 结构
{OUTPUT_SCHEMA_TEXT}

# 标注规则（必须遵守）
1. 逐段读完，不得因篇幅长而截断或只输出前几个站点。重点是“所有真实应改站点”。
2. 正文 [M] 与摘要 [S] 是两个独立 scope；同一句在两处都存在且都需改时，输出两个 target，
   分别标 scope=main/summary。摘要中不存在的章节不要硬造。
3. 同一规则在同一 scope 有多个独立段落（例如 G17 用途句分两段、G02/G04 的 A 组和 C 组
   需要分别替换）时，每个实际站点各一条 target。同一段落内需要两处不同修改（如 G05 的
   费率词和备案短语）时，也各一条 target。
4. 只改指引授权范围内的内容。范围外不润色、不去重、不新增、不删除独立句。尤其：
   - G05 只标“基金的基本情况-份额类别设置”中的费率调整条款；不要标基金份额持有人大会、
     估值差错、合同变更等其他含“调低赎回费率/并报中国证监会备案”的段落。
   - G06 只删除“不同基金份额类别之间不得互相转换”的限制；单向的“Y类基金份额不能转换为
     A/C/F类”不是本规则目标。
   - G15 只删除销售服务费的旧支付安排（包括 5/10 个工作日、自动支付、无需划付指令等变体），
     不要删除管理费、托管费或销售服务费费率/计提公式。
   - G17 只删除销售服务费用途/使用范围句，不要删除费率或支付安排。
   - G12 与 G13 常在同一段：G12 只替换“赎回费用归入基金财产的比例……”这一句，old_text 不得包含
     “对持续持有期少于7日的投资者收取不低于1.50%的赎回费……”；G13 必须另出一条 delete 目标
     删除该7日句。不要把 G13 的句子塞进 G12 的 old_text/required_text。
   - G18 只在存在“由于本基金A类不收取销售服务费，而C类收取……”或同义旧原因句时替换；
     若原文已经用中性句完整表达“各份额类别费用收取不同→可分配收益不同”，记 satisfied；
     若根本没有对应原因句，记 not_applicable 并说明“替换旧句不存在，且指引未授权强制新增”，
     不要新增 G18 句子。
5. 份额类别必须按原件事实，不得把指引的 A/C 示例强加给 A/D/Y/E 等真实类别：
   - 先列全实际类别，再判断哪些类别收申购费、哪些计提销售服务费。
   - G02/G04/G07/G08/G10/G11/G14/G16/G18/G22 的新文要按实际收费组替换；若实际就是 A/C
     且原文已符合，记 satisfied，不要制造无意义的同文替换。
   - 若产品没有销售服务费类别（如 A/Y 且均不计提销售服务费），不要编造 C 类或销售服务费
     句子；G15–G17 记 not_applicable；G01/G03 只保留实际存在的申购费直销豁免部分。
   - QDII 的 A/C 类别内再有人民币/美元份额时，类别分组仍按 A/C 收费组；不要把币种份额
     当成新的收费类别。
6. 单类别/多类别分支：
   - 单类别：G07、G10 适用；G09、G11、G18、G22 不适用；G21 为 noop。
   - 多类别：G08、G09、G11 适用；G07、G10 不适用；G18 视原因句；G22 在非浮动管理费且
     有销售服务费时适用。
   - G19/G20 仅在浮动管理费产品；本批如无“超额管理费/或有管理费/浮动管理费”证据，
     记 not_applicable。
7. G01/G03 是新条款追加，不是替换。锚点必须是真正的份额类别定义段（含“称为…类基金份额”
   或“将基金份额分为…”），不能锚到 G05 的费率调整条款。摘要中没有类别定义就不要追加。
8. G16 是追加新机制：锚点应在销售服务费小节的最后（费率/计提公式之后、下一小节之前），
   不能锚到将被 G15 删除的支付段，也不能锚到 G17 用途段。正文和摘要各有销售服务费小节时
   分别追加。
9. 旧文定位：
   - replace/delete 的 old_text 必须是该段逐字连续子串；不要带省略号，不要把整段无关文字
     都塞进 old_text。delete 只取要删除的句子/短语。
   - required_text 是 old_text 的替换文本（不是整段重写）；append 的 required_text 是完整
     追加文本。
10. 事实必须带原文 quote 和段号：基金类型/是否适用、全部份额类别及申购费/销售服务费极性、
    是否有销售服务费、是否浮动管理费、渠道政策、持有满一年规则、支付机制。没有证据写 null
    并列入 uncertain，不要猜。
11. 若无法判断某规则是否适用，status=unknown 并写清缺口；不要把 unknown 直接写成
    not_applicable。已满足必须有原文证据；不适用必须写条件/缺失依据。
12. 不要引用或猜测任何引擎结果、历史标签、报告或文件名规则；只依据本合同和指引。
"""


def review_prompt(doc: DocModel, guide_text: str, labels: dict[str, Any]) -> str:
    compact_labels = {
        "fund": labels.get("fund"),
        "rule_coverage": labels.get("rule_coverage"),
        "targets": labels.get("targets"),
        "uncertain": labels.get("uncertain"),
    }
    return f"""
# 任务
你是独立复核人。请对照指引和合同原文，复核下面这份独立标签是否完整、准确。
重点找：
1. 漏掉的实际应改站点（尤其正文/摘要重复、同规则多段落、G05 误选其他章节、G15/G17 边界）；
2. 不存在的目标、越界修改、把已满足/不适用误标为 target；
3. old_text/required_text/paragraph_index 是否与原文一致，append 锚点是否错误；
4. 份额类别与收费事实（A/C、A/Y、A/C/E、QDII 币种份额、单/多类别、浮动管理费）是否正确；
5. satisfied/not_applicable/unknown 是否有证据支撑。
只报告确有原件依据的问题；不确定的放 uncertain，不要为了凑数报问题。

# 指引规则
{guide_text}

# 合同原文
{contract_prompt(doc)}

# 待复核标签
{json.dumps(compact_labels, ensure_ascii=False, indent=1)}

# 输出 JSON
{{
  "verdict": "pass|issues|uncertain",
  "missing_targets": [
    {{"rule_id": "G01", "scope": "main|summary", "paragraph_index": 0,
      "old_text": "逐字原文", "required_text": "应替换/追加文字", "reason": "依据"}}
  ],
  "incorrect_targets": [
    {{"target_id": "B02-T01", "issue": "问题", "suggested_fix": "建议"}}
  ],
  "fact_issues": [{{"field": "share_classes", "issue": "问题", "evidence": "原文/段号"}}],
  "status_issues": [{{"rule_id": "G01", "scope": "main", "issue": "问题", "suggested_status": "satisfied|not_applicable|unknown|target"}}],
  "uncertain": [{{"rule_id": "G01", "scope": "main", "issue": "无法确定点"}}]
}}
"""


def adjudication_prompt(doc: DocModel, guide_text: str, findings: dict[str, Any]) -> str:
    return f"""
# 任务
独立复核人提出了以下疑似问题。请你作为原标注人，对照指引和合同原文逐条裁定。
只接受有逐字原文依据、且属于规则授权范围的问题；范围外、重复、无授权新增的应拒绝。
无法确定的标 uncertain。

# 指引规则
{guide_text}

# 合同原文
{contract_prompt(doc)}

# 复核发现
{json.dumps(findings, ensure_ascii=False, indent=1)}

# 输出 JSON
{{
  "decisions": [
    {{"finding_id": "F1", "decision": "accept|reject|uncertain", "reason": "依据",
      "target": {{"rule_id": "G01", "op": "append|replace|delete", "scope": "main|summary",
                  "paragraph_index": 0, "old_text": "", "required_text": "",
                  "source_quote": "", "anchor_quote": null, "anchor_position": null,
                  "requirement": "", "class_scope": [], "guide_paragraphs": [], "rationale": ""}} 或 null,
      "suggested_fix": "对 incorrect_target 的修正文字" 或 null}}
  ]
}}
"""


def section_scope_ok(rule_id: str, para: Para) -> bool:
    path = para.section_path or ""
    if rule_id in {"G01", "G02"}:
        return "释义" in path
    if rule_id in {"G03", "G04", "G05", "G06"}:
        return "基金的基本情况" in path
    if rule_id in {f"G{i:02d}" for i in range(7, 15)}:
        return ("申购" in path and ("赎回" in path or "费用" in path)) and "基金费用" not in path
    if rule_id in {"G15", "G16", "G17"}:
        return ("基金费用" in path or "费用" in path or "销售服务费" in path) and "申购" not in path
    if rule_id == "G18":
        return "收益" in path and "分配" in path
    if rule_id in {"G19", "G20", "G21", "G22"}:
        return "清算" in path and "剩余资产" in path
    return False


CANDIDATE_PATTERNS: dict[str, list[str]] = {
    "G01": [r"基金份额类别", r"将基金份额分为"],
    "G02": [r"基金份额类别", r"将基金份额分为"],
    "G03": [r"基金份额类别", r"将基金份额分为"],
    "G04": [r"基金份额类别", r"将基金份额分为"],
    "G05": [r"调低赎回费率", r"并报中国证监会备案"],
    "G06": [r"不得互相转换", r"不同基金份额类别之间不得"],
    "G07": [r"申购费率由基金管理人决定"],
    "G08": [r"申购费率由基金管理人决定"],
    "G09": [r"赎回金额为按实际确认的有效赎回份额"],
    "G10": [r"申购费用由投资人承担，不列入基金财产"],
    "G11": [r"申购费用由投资人承担，不列入基金财产"],
    "G12": [r"赎回费用归入基金财产的比例"],
    "G13": [r"持续持有期少于7日"],
    "G14": [r"适当调低.*申购费率"],
    "G15": [r"销售服务费", r"工作日|划付指令|自动|按月支付|每日计提"],
    "G16": [r"销售服务费"],
    "G17": [r"销售服务费主要用于支付销售机构佣金", r"销售服务费的使用范围不包括"],
    "G18": [r"不收取销售服务费，而", r"费用收取不同", r"可分配收益将有所不同", r"可供分配利润将有所不同"],
    "G19": [r"超额管理费", r"或有管理费"],
    "G20": [r"超额管理费", r"或有管理费"],
    "G21": [r"全部剩余资产"],
    "G22": [r"全部剩余资产"],
}


def candidate_sites(rule_id: str, doc: DocModel) -> list[int]:
    patterns = [re.compile(p) for p in CANDIDATE_PATTERNS.get(rule_id, [])]
    hits: list[int] = []
    any_mode = rule_id in {
        "G05", "G06", "G17", "G18", "G19", "G20",
    }
    for para in doc.nonempty():
        if not section_scope_ok(rule_id, para):
            continue
        text = para.text
        if rule_id in {"G01", "G02", "G03", "G04"}:
            if "基金份额类别" not in text and "将基金份额分为" not in text:
                continue
            if "称为" not in text and "将基金份额分为" not in text:
                continue
        if rule_id == "G15":
            if "销售服务费" not in text:
                continue
            if not re.search(r"工作日|划付指令|自动|按月支付|每日计提", text):
                continue
            hits.append(para.index)
            continue
        if rule_id == "G16":
            # G16 is an append at the end of the sales-service-fee subsection.
            # Do not require one coverage entry per sales-service paragraph;
            # the subsection's existence is enough to require a G16 decision.
            if "销售服务费" in text:
                hits.append(para.index)
            continue
        matched = any(p.search(text) for p in patterns) if any_mode else all(p.search(text) for p in patterns)
        if matched:
            hits.append(para.index)
    return hits


def required_scopes(doc: DocModel) -> dict[str, set[str]]:
    required = {"main": set(RULE_IDS)}
    if doc.summary_start is None:
        return required
    heads = " ".join(doc.summary_headings)
    summary: set[str] = set()
    if "释义" in heads or "基金份额类别" in heads:
        summary.update({"G01", "G02", "G03", "G04", "G05", "G06"})
    if "申购" in heads and "赎回" in heads:
        summary.update({f"G{i:02d}" for i in range(7, 15)})
    if "费用" in heads or "销售服务费" in heads:
        summary.update({"G15", "G16", "G17"})
    if "收益" in heads:
        summary.add("G18")
    if "清算" in heads:
        summary.update({"G19", "G20", "G21", "G22"})
    if summary:
        required["summary"] = summary
    return required


def audit_coverage(doc: DocModel, coverage: list[dict[str, Any]], targets: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    required = required_scopes(doc)
    coverage_keys = {(c.get("rule_id"), c.get("scope")) for c in coverage}
    for scope, rules in required.items():
        for rule_id in sorted(rules):
            if (rule_id, scope) not in coverage_keys:
                issues.append(f"缺少 rule_coverage：{rule_id}/{scope}")
    for rule_id in RULE_IDS:
        candidates = candidate_sites(rule_id, doc)
        if not candidates:
            continue
        scopes_present = {
            "summary" if doc.paragraphs[c].is_summary else "main"
            for c in candidates
        }
        for scope in scopes_present:
            if not any(
                c.get("rule_id") == rule_id and c.get("scope") == scope
                for c in coverage
            ):
                issues.append(f"候选站点未覆盖：{rule_id}/{scope}（合同存在候选段落）")
    return issues


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        match = re.search(r"\d+", value)
        if match:
            return int(match.group(0))
    return None


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _normalize_status(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return STATUS_ALIASES.get(text, "unknown")


def _normalize_op(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"insert", "append", "add"}:
        return "append"
    if text in {"remove", "delete", "del"}:
        return "delete"
    if text in {"replace", "modify", "update", "change"}:
        return "replace"
    return text


def normalize_facts(raw: dict[str, Any], doc: DocModel) -> tuple[dict[str, Any], list[str]]:
    issues: list[str] = []
    fund_raw = raw.get("fund") or raw.get("facts") or {}
    if not isinstance(fund_raw, dict):
        fund_raw = {}
    classes_raw = _first(fund_raw, "share_classes", "classes", "class_list") or []
    classes: list[dict[str, Any]] = []
    if isinstance(classes_raw, list):
        for item in classes_raw:
            if not isinstance(item, dict):
                continue
            label = str(_first(item, "label", "class", "name") or "").strip()
            label = re.sub(r"类基金份额$", "", label)
            evidence = _first(item, "evidence", "evidence_quote", "quote")
            evidence_obj = evidence if isinstance(evidence, dict) else {}
            para_idx = _as_int(_first(evidence_obj, "paragraph_index", "paragraph", "index"))
            quote = _first(evidence_obj, "quote", "text") if isinstance(evidence_obj, dict) else evidence
            if para_idx is None:
                para_idx = _as_int(_first(item, "paragraph_index", "paragraph"))
            classes.append({
                "label": label,
                "pays_purchase_fee": item.get("pays_purchase_fee", item.get("purchase_fee")),
                "charges_sales_service_fee": item.get(
                    "charges_sales_service_fee", item.get("sales_service_fee")
                ),
                "evidence": {"paragraph_index": para_idx, "quote": quote} if quote else None,
            })
    class_count = _as_int(_first(fund_raw, "class_count", "classes_count"))
    if class_count is None and classes:
        class_count = len(classes)
    has_service = fund_raw.get("has_sales_service_fee")
    if has_service is None and classes:
        vals = [c.get("charges_sales_service_fee") for c in classes]
        if any(v is True for v in vals):
            has_service = True
        elif vals and all(v is False for v in vals):
            has_service = False
    float_fee = fund_raw.get("floating_management_fee")
    float_evidence = _first(fund_raw, "floating_fee_evidence", "floating_evidence")
    if float_evidence is not None and not isinstance(float_evidence, dict):
        float_evidence = None
    payment = fund_raw.get("payment_mechanism")
    if not isinstance(payment, dict):
        payment = {}
    fund = {
        "name": _first(fund_raw, "name", "fund_name"),
        "fund_type": _first(fund_raw, "fund_type", "type", "product_type"),
        "fund_type_evidence": _first(fund_raw, "fund_type_evidence", "type_evidence"),
        "eligible": fund_raw.get("eligible"),
        "eligibility_reason": _first(fund_raw, "eligibility_reason", "eligible_reason"),
        "eligibility_evidence": _first(fund_raw, "eligibility_evidence", "eligible_evidence"),
        "share_classes": classes,
        "class_count": class_count,
        "has_sales_service_fee": has_service,
        "floating_management_fee": float_fee,
        "floating_fee_evidence": float_evidence,
        "direct_sales_exemption_present": fund_raw.get("direct_sales_exemption_present"),
        "one_year_holding_rule_present": fund_raw.get("one_year_holding_rule_present"),
        "payment_mechanism": {
            "old_arrangement_present": payment.get("old_arrangement_present"),
            "working_days": payment.get("working_days"),
            "evidence": payment.get("evidence"),
        },
    }
    if not fund["fund_type"]:
        issues.append("fund_type missing")
    if fund["eligible"] is None:
        issues.append("eligible missing")
    if not classes:
        issues.append("share_classes missing")
    if class_count is None:
        issues.append("class_count missing")
    if has_service is None:
        issues.append("has_sales_service_fee unknown")
    if float_fee is None:
        issues.append("floating_management_fee unknown")
    float_keywords = ("超额管理费", "或有管理费", "浮动管理费", "业绩报酬")
    keyword_hits = [
        p.index for p in doc.nonempty()
        if any(keyword in p.text for keyword in float_keywords)
    ]
    if float_fee is False and not keyword_hits:
        fund["floating_fee_evidence"] = None
        fund["floating_fee_basis"] = "keyword_absent_in_full_contract"
    elif float_fee is True:
        evidence = fund.get("floating_fee_evidence")
        quote = evidence.get("quote") if isinstance(evidence, dict) else ""
        if not keyword_hits or not any(keyword in str(quote or "") for keyword in float_keywords):
            issues.append("floating_management_fee=true without floating-fee evidence")
        fund["floating_fee_basis"] = "model_true_with_evidence"
    else:
        fund["floating_fee_basis"] = "model_false_with_evidence_or_conflict"
    return fund, issues


def normalize_targets(raw_targets: Any, doc: DocModel, rule_map: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    issues: list[str] = []
    targets: list[dict[str, Any]] = []
    if not isinstance(raw_targets, list):
        return targets, ["targets not a list"]
    for nr, raw in enumerate(raw_targets, 1):
        if not isinstance(raw, dict):
            continue
        rule_id = str(_first(raw, "rule_id", "rule", "id") or "").strip().upper()
        if rule_id not in RULE_IDS:
            issues.append(f"target {nr}: invalid rule_id {rule_id!r}")
            continue
        op = _normalize_op(_first(raw, "op", "operation", "action"))
        if op not in ALLOWED_OPS[rule_id]:
            issues.append(f"target {nr} {rule_id}: invalid op {op!r}")
            continue
        scope = str(_first(raw, "scope", "site_scope", "location_scope") or "main").lower()
        if scope not in {"main", "summary"}:
            scope = "summary" if "摘要" in scope else "main"
        para_idx = _as_int(_first(raw, "paragraph_index", "paragraph", "para_index", "paragraph_id"))
        if para_idx is None or not (0 <= para_idx < len(doc.paragraphs)):
            issues.append(f"target {nr} {rule_id}: invalid paragraph_index {para_idx!r}")
            continue
        para = doc.paragraphs[para_idx]
        if not para.text.strip():
            issues.append(f"target {nr} {rule_id}: empty paragraph p{para_idx}")
            continue
        if scope == "summary" and not para.is_summary:
            issues.append(f"target {nr} {rule_id}: scope=summary but p{para_idx} is main")
        if scope == "main" and para.is_summary:
            issues.append(f"target {nr} {rule_id}: scope=main but p{para_idx} is summary")
        if not section_scope_ok(rule_id, para):
            issues.append(
                f"target {nr} {rule_id}: p{para_idx} outside expected section ({para.section_path})"
            )
        old_text = str(_first(raw, "old_text", "old", "source_text") or "")
        required_text = str(_first(raw, "required_text", "new_text", "replacement", "new") or "")
        source_quote = str(_first(raw, "source_quote", "quote", "evidence_quote") or "")
        anchor_quote = _first(raw, "anchor_quote", "anchor")
        anchor_position = _first(raw, "anchor_position", "position")
        if op == "append":
            if old_text:
                issues.append(f"target {nr} {rule_id}: append old_text must be empty")
            if not required_text.strip():
                issues.append(f"target {nr} {rule_id}: append required_text empty")
            if anchor_quote is None:
                anchor_quote = para.text
            anchor_span = find_span(para.text, str(anchor_quote)) if anchor_quote else None
            if anchor_span is None:
                issues.append(f"target {nr} {rule_id}: append anchor_quote not in p{para_idx}")
                anchor_quote = para.text
                anchor_span = (0, len(para.text))
            source_quote = str(anchor_quote)
            start = end = len(compact(para.text))
            old_span = None
            anchor_position = "end_of_paragraph"
        else:
            if not old_text:
                issues.append(f"target {nr} {rule_id}: {op} old_text empty")
                continue
            span = find_span(para.text, old_text)
            if span is None:
                issues.append(f"target {nr} {rule_id}: old_text not found in p{para_idx}: {old_text[:60]!r}")
                continue
            start, end = span
            old_text = para.text[start:end]
            if not source_quote or find_span(para.text, source_quote) is None:
                source_quote = old_text
            old_span = (start, end)
            anchor_quote = None
            anchor_position = None
            if op == "delete" and required_text.strip():
                issues.append(f"target {nr} {rule_id}: delete required_text must be empty")
            if op == "replace" and not required_text.strip():
                issues.append(f"target {nr} {rule_id}: replace required_text empty")
        cstart, cend = compact_offsets(para.text, start, end)
        if old_span is not None:
            assert compact(para.text)[cstart:cend] == compact(old_text)
        target = {
            "rule_id": rule_id,
            "group": rule_id,
            "op": op,
            "scope": scope,
            "site_scope": scope,
            "paragraph_index": para_idx,
            "location": para.section_path,
            "old_text": old_text,
            "required_text": required_text,
            "source_quote": source_quote,
            "anchor_quote": anchor_quote if op == "append" else None,
            "anchor_position": anchor_position if op == "append" else None,
            "requirement": str(_first(raw, "requirement", "obligation") or rule_map[rule_id].get("requirement") or ""),
            "class_scope": raw.get("class_scope") if isinstance(raw.get("class_scope"), list) else [],
            "guide_paragraphs": raw.get("guide_paragraphs") if isinstance(raw.get("guide_paragraphs"), list) else rule_map[rule_id].get("source_paragraphs", []),
            "rationale": str(_first(raw, "rationale", "reason") or ""),
            "compact_start": cstart,
            "compact_end": cend,
            "old_text_sha256": sha256_bytes(compact(old_text).encode("utf-8")),
            "paragraph_text_sha256": sha256_bytes(para.text.encode("utf-8")),
            "confidence": "high",
            "review_flags": [],
        }
        targets.append(target)
    # stable ordering and ids
    targets.sort(key=lambda t: (t["paragraph_index"], RULE_IDS.index(t["rule_id"]), t["op"], t["compact_start"]))
    for idx, target in enumerate(targets, 1):
        target["target_id"] = f"T{idx:03d}"
    # relate main/summary counterparts by rule/op/normalized required text
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for target in targets:
        key = (target["rule_id"], target["op"], compact(target["required_text"]))
        groups.setdefault(key, []).append(target)
    for group in groups.values():
        if len(group) > 1:
            for target in group:
                target["related_target_ids"] = [
                    other["target_id"] for other in group if other is not target
                ]
    for target in targets:
        target.setdefault("related_target_ids", [])
    return targets, issues


def normalize_coverage(raw_coverage: Any, targets: list[dict[str, Any]], doc: DocModel) -> tuple[list[dict[str, Any]], list[str]]:
    issues: list[str] = []
    coverage: list[dict[str, Any]] = []
    if not isinstance(raw_coverage, list):
        return coverage, ["rule_coverage not a list"]
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for item in raw_coverage:
        if not isinstance(item, dict):
            continue
        rule_id = str(_first(item, "rule_id", "rule", "id") or "").strip().upper()
        if rule_id not in RULE_IDS:
            issues.append(f"coverage: invalid rule_id {rule_id!r}")
            continue
        scope = str(_first(item, "scope", "site_scope") or "main").lower()
        if scope not in {"main", "summary"}:
            scope = "summary" if "摘要" in scope else "main"
        status = _normalize_status(_first(item, "status", "result", "coverage"))
        para_idx = _as_int(_first(item, "paragraph_index", "paragraph", "para_index"))
        if para_idx is not None and not (0 <= para_idx < len(doc.paragraphs)):
            para_idx = None
        entry = {
            "rule_id": rule_id,
            "scope": scope,
            "status": status,
            "paragraph_index": para_idx,
            "reason": str(_first(item, "reason", "basis", "note") or ""),
            "evidence_quote": _first(item, "evidence_quote", "quote", "evidence"),
        }
        key = (rule_id, scope)
        if key in seen:
            previous = seen[key]
            # A target wins; unknown is more honest than silently dropping.
            order = {"target": 4, "unknown": 3, "satisfied": 2, "not_applicable": 1}
            if order.get(status, 0) > order.get(previous["status"], 0):
                seen[key] = entry
        else:
            seen[key] = entry
    # Ensure every target has a target coverage entry.
    for target in targets:
        key = (target["rule_id"], target["scope"])
        if key not in seen:
            seen[key] = {
                "rule_id": target["rule_id"],
                "scope": target["scope"],
                "status": "target",
                "paragraph_index": target["paragraph_index"],
                "reason": "target derived from targets array",
                "evidence_quote": target["source_quote"],
            }
        elif seen[key]["status"] != "target":
            seen[key]["status"] = "target"
            seen[key]["reason"] = "target derived from targets array"
    coverage = sorted(seen.values(), key=lambda c: (c["scope"], RULE_IDS.index(c["rule_id"])))
    return coverage, issues


def derive_lists(coverage: list[dict[str, Any]], targets: list[dict[str, Any]]) -> tuple[list, list, list, list]:
    satisfied = []
    not_applicable = []
    unknown = []
    target_cov = []
    for entry in coverage:
        if entry["status"] == "target":
            target_cov.append(entry)
        elif entry["status"] == "satisfied":
            satisfied.append(entry)
        elif entry["status"] == "not_applicable":
            not_applicable.append(entry)
        else:
            unknown.append(entry)
    return satisfied, not_applicable, unknown, target_cov


def validate_required_text(target: dict[str, Any], fund: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    rule = target["rule_id"]
    text = compact(target.get("required_text", ""))
    op = target["op"]
    if op == "delete":
        if text:
            issues.append(f"{target.get('target_id')} {rule}: delete required_text not empty")
        return issues
    if rule in {"G01", "G03"}:
        if "直销机构" not in text:
            issues.append(f"{target.get('target_id')} {rule}: appended text lacks 直销机构")
        if "不收取" not in text:
            issues.append(f"{target.get('target_id')} {rule}: appended text lacks 不收取")
        if fund.get("has_sales_service_fee") and "销售服务费" not in text:
            issues.append(f"{target.get('target_id')} {rule}: service-fee product but text lacks 销售服务费")
    elif rule == "G16":
        if not text.startswith("销售服务费每日计提"):
            issues.append(f"{target.get('target_id')} G16: text should start 销售服务费每日计提")
        for token in ("直销机构", "5个工作日", "超过一年"):
            if token not in text:
                issues.append(f"{target.get('target_id')} G16: text lacks {token}")
    elif rule in {"G07", "G08", "G10", "G11"}:
        if "直销机构" not in text or "申购费" not in text:
            issues.append(f"{target.get('target_id')} {rule}: text lacks 直销机构/申购费")
    elif rule == "G09":
        if "扣除或加上" not in text:
            issues.append(f"{target.get('target_id')} G09: text lacks 扣除或加上")
    elif rule == "G12":
        if "全额计入基金财产" not in text:
            issues.append(f"{target.get('target_id')} G12: text lacks 全额计入基金财产")
    elif rule == "G14":
        multi = (fund.get("class_count") or 0) > 1
        if multi and "销售服务费率" not in text:
            issues.append(f"{target.get('target_id')} G14: multi-class text lacks 销售服务费率")
        if not multi and "赎回费率" in text:
            issues.append(f"{target.get('target_id')} G14: single-class text still has 赎回费率")
    elif rule == "G18":
        if "费用收取不同" not in text and "费用收取上不同" not in text:
            issues.append(f"{target.get('target_id')} G18: text lacks 费用收取不同")
    elif rule == "G19":
        if "或有管理费" not in text or "超额管理费" not in text:
            issues.append(f"{target.get('target_id')} G19: text lacks floating-fee terms")
    elif rule == "G20":
        if "销售服务费" not in text or "超额管理费" not in text:
            issues.append(f"{target.get('target_id')} G20: text lacks 销售服务费/超额管理费")
    elif rule == "G22":
        if "销售服务费" not in text:
            issues.append(f"{target.get('target_id')} G22: text lacks 销售服务费")
    return issues


def locate_quote(doc: DocModel, quote: str) -> int | None:
    hits = [p.index for p in doc.nonempty() if find_span(p.text, quote) is not None]
    return hits[0] if len(hits) == 1 else (hits[0] if hits else None)


def _relocate(evidence: Any, doc: DocModel) -> bool:
    if not isinstance(evidence, dict):
        return False
    quote = evidence.get("quote")
    if not quote:
        return False
    para_idx = _as_int(evidence.get("paragraph_index"))
    if para_idx is not None and 0 <= para_idx < len(doc.paragraphs):
        if find_span(doc.paragraphs[para_idx].text, str(quote)) is not None:
            return True
    located = locate_quote(doc, str(quote))
    if located is not None:
        evidence["paragraph_index"] = located
        return True
    return False


def validate_evidence(fund: dict[str, Any], doc: DocModel) -> list[str]:
    issues: list[str] = []
    for field_name in ("fund_type_evidence", "eligibility_evidence", "floating_fee_evidence"):
        evidence = fund.get(field_name)
        if not isinstance(evidence, dict):
            continue
        para_idx = _as_int(evidence.get("paragraph_index"))
        quote = evidence.get("quote")
        if not _relocate(evidence, doc):
            issues.append(f"{field_name}: quote not located")
            continue
    for cls in fund.get("share_classes") or []:
        evidence = cls.get("evidence")
        if not isinstance(evidence, dict):
            issues.append(f"class {cls.get('label')}: missing evidence")
            continue
        para_idx = _as_int(evidence.get("paragraph_index"))
        quote = evidence.get("quote")
        if not _relocate(evidence, doc):
            issues.append(f"class {cls.get('label')}: evidence quote not located")
    payment = fund.get("payment_mechanism") or {}
    ev = payment.get("evidence")
    if isinstance(ev, dict):
        para_idx = _as_int(ev.get("paragraph_index"))
        quote = ev.get("quote")
        if not _relocate(ev, doc):
            issues.append("payment_mechanism: evidence quote not located")
    return issues


def _sentence_span(text: str, phrase_start: int) -> tuple[int, int]:
    start = phrase_start
    while start > 0 and text[start - 1] not in "。！？；":
        start -= 1
    end = phrase_start
    while end < len(text) and text[end] not in "。！？":
        end += 1
    if end < len(text):
        end += 1
    return start, end


def drop_noop_replacements(
    targets: list[dict[str, Any]],
    coverage: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Drop replace targets whose required text equals the old text.

    A no-op replacement is not a real modification site; the guide's class
    substitution explicitly says an A/C-only contract is already satisfied.
    """
    notes: list[str] = []
    keep: list[dict[str, Any]] = []
    for target in targets:
        if target["op"] == "replace" and compact(target["old_text"]) == compact(target["required_text"]):
            notes.append(
                f"dropped no-op replacement {target['rule_id']} p{target['paragraph_index']}"
            )
            for cov in coverage:
                if cov["rule_id"] == target["rule_id"] and cov["scope"] == target["scope"]:
                    cov["status"] = "satisfied"
                    cov["paragraph_index"] = target["paragraph_index"]
                    cov["evidence_quote"] = target["old_text"]
                    cov["reason"] = "no-op replacement: original text already matches the required grouping"
            continue
        keep.append(target)
    keep.sort(key=lambda t: (t["paragraph_index"], RULE_IDS.index(t["rule_id"]), t["op"], t["compact_start"]))
    for idx, target in enumerate(keep, 1):
        target["target_id"] = f"T{idx:03d}"
    return keep, coverage, notes


def ensure_g13_targets(
    targets: list[dict[str, Any]],
    coverage: list[dict[str, Any]],
    doc: DocModel,
    rule_map: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Split a G12+G13 combined target and add exact G13 delete sites.

    This is a deterministic completion from the guide's exact G13 old text; it
    does not invent targets or use engine output. It guards against the common
    model error of folding the 7-day sentence into G12.
    """
    notes: list[str] = []
    phrase_re = re.compile(r"对持续持有期少于7[日天]")
    existing = {
        (t["rule_id"], t["scope"], t["paragraph_index"])
        for t in targets if t["rule_id"] == "G13"
    }
    for para in doc.nonempty():
        if not section_scope_ok("G13", para):
            continue
        match = phrase_re.search(para.text)
        if not match:
            continue
        start, end = _sentence_span(para.text, match.start())
        old_text = para.text[start:end]
        if "赎回费" not in old_text:
            continue
        # Trim any G12 target on this paragraph that swallowed the G13 sentence.
        for target in targets:
            if target["rule_id"] != "G12" or target["paragraph_index"] != para.index:
                continue
            span = find_span(para.text, target["old_text"])
            if span and span[0] <= start and span[1] >= end:
                trimmed_end = start
                while trimmed_end > span[0] and para.text[trimmed_end - 1].isspace():
                    trimmed_end -= 1
                if trimmed_end > span[0]:
                    target["old_text"] = para.text[span[0]:trimmed_end]
                    target["old_text_sha256"] = sha256_bytes(compact(target["old_text"]).encode("utf-8"))
                    target["compact_start"], target["compact_end"] = compact_offsets(para.text, span[0], trimmed_end)
                    target["rationale"] = (target.get("rationale", "") + " [G13 sentence split out by guide-exact completion]").strip()
                    notes.append(f"split G13 sentence out of G12 target p{para.index}")
        key = ("G13", para.is_summary and "summary" or "main", para.index)
        if key in existing:
            continue
        cstart, cend = compact_offsets(para.text, start, end)
        target = {
            "rule_id": "G13",
            "group": "G13",
            "op": "delete",
            "scope": "summary" if para.is_summary else "main",
            "site_scope": "summary" if para.is_summary else "main",
            "paragraph_index": para.index,
            "location": para.section_path,
            "old_text": old_text,
            "required_text": "",
            "source_quote": old_text,
            "anchor_quote": None,
            "anchor_position": None,
            "requirement": rule_map["G13"].get("requirement", ""),
            "class_scope": [],
            "guide_paragraphs": rule_map["G13"].get("source_paragraphs", []),
            "rationale": "guide-exact completion: delete the 7-day redemption-fee sentence",
            "compact_start": cstart,
            "compact_end": cend,
            "old_text_sha256": sha256_bytes(compact(old_text).encode("utf-8")),
            "paragraph_text_sha256": sha256_bytes(para.text.encode("utf-8")),
            "confidence": "high",
            "review_flags": ["coverage_completion"],
            "provenance": "guide_exact_completion",
        }
        targets.append(target)
        existing.add(key)
        cov_key = ("G13", target["scope"])
        if not any(c["rule_id"] == "G13" and c["scope"] == target["scope"] for c in coverage):
            coverage.append({
                "rule_id": "G13",
                "scope": target["scope"],
                "status": "target",
                "paragraph_index": para.index,
                "reason": "guide-exact completion of 7-day sentence deletion",
                "evidence_quote": old_text,
            })
        else:
            for cov in coverage:
                if cov["rule_id"] == "G13" and cov["scope"] == target["scope"]:
                    cov["status"] = "target"
                    cov["paragraph_index"] = para.index
                    cov["evidence_quote"] = old_text
                    cov["reason"] = (cov.get("reason", "") + " [guide-exact site added]").strip()
    targets.sort(key=lambda t: (t["paragraph_index"], RULE_IDS.index(t["rule_id"]), t["op"], t["compact_start"]))
    for idx, target in enumerate(targets, 1):
        target["target_id"] = f"T{idx:03d}"
    return targets, coverage, notes


def mandatory_checks(
    doc: DocModel,
    fund: dict[str, Any],
    coverage: list[dict[str, Any]],
    targets: list[dict[str, Any]],
) -> list[str]:
    """Deterministic completeness guards from guide conditions and real facts.

    These do not create labels; they turn an objectively required site that the
    model marked not_applicable into a repair request for the same model.
    """
    issues: list[str] = []
    class_count = fund.get("class_count")
    multi = isinstance(class_count, int) and class_count > 1
    single = class_count == 1
    has_service = fund.get("has_sales_service_fee")
    floating = fund.get("floating_management_fee")

    def has_target(rule_id: str, candidates: Iterable[int] | None = None) -> bool:
        for target in targets:
            if target["rule_id"] != rule_id:
                continue
            if candidates is None or target["paragraph_index"] in set(candidates):
                return True
        return False

    def candidate_paras(rule_id: str, predicate) -> list[int]:
        return [
            p.index for p in doc.nonempty()
            if section_scope_ok(rule_id, p) and predicate(p.text)
        ]

    # G07/G08
    base_apply = re.compile(r"申购费率由基金管理人决定")
    for idx in candidate_paras("G07", lambda t: bool(base_apply.search(t))):
        if multi and not has_target("G08", [idx]):
            issues.append(f"G08 missing target at p{idx}: multi-class purchase-fee sentence must change")
        if single and not has_target("G07", [idx]):
            issues.append(f"G07 missing target at p{idx}: single-class purchase-fee sentence must change")
    # G09
    base_redeem = re.compile(r"赎回金额为按实际确认的有效赎回份额")
    for idx in candidate_paras("G09", lambda t: bool(base_redeem.search(t))):
        text = doc.paragraphs[idx].text
        if multi and "扣除相应的费用" in text and "扣除或加上" not in text and not has_target("G09", [idx]):
            issues.append(f"G09 missing target at p{idx}: multi-class redemption calculation must change")
    # G10/G11
    base_bear = re.compile(r"申购费用由投资人承担，不列入基金财产")
    for idx in candidate_paras("G10", lambda t: bool(base_bear.search(t))):
        if multi and not has_target("G11", [idx]):
            issues.append(f"G11 missing target at p{idx}: multi-class purchase-fee bearer clause must change")
        if single and not has_target("G10", [idx]):
            issues.append(f"G10 missing target at p{idx}: single-class purchase-fee bearer clause must change")
    # G12
    base_g12 = re.compile(r"赎回费用归入基金财产的比例")
    for idx in candidate_paras("G12", lambda t: bool(base_g12.search(t))):
        if not has_target("G12", [idx]):
            issues.append(f"G12 missing target at p{idx}: redemption-fee attribution clause must change")
    # G14
    base_g14 = re.compile(r"适当调低.*申购费率")
    for idx in candidate_paras("G14", lambda t: bool(base_g14.search(t))):
        if not has_target("G14", [idx]):
            issues.append(f"G14 missing target at p{idx}: promotion fee-change sentence must change")
    # G15
    for idx in candidate_paras("G15", lambda t: "销售服务费" in t and bool(re.search(r"工作日|划付指令|自动|按月支付|每日计提", t))):
        if not has_target("G15", [idx]):
            issues.append(f"G15 missing target at p{idx}: sales-service-fee payment arrangement must be deleted")
    # G16
    if has_service is True:
        fee_paras = candidate_paras("G16", lambda t: "销售服务费" in t)
        for idx in fee_paras:
            scope = "summary" if doc.paragraphs[idx].is_summary else "main"
            if not any(
                c["rule_id"] == "G16" and c["scope"] == scope and c["status"] in {"target", "satisfied"}
                for c in coverage
            ) and not has_target("G16"):
                issues.append(f"G16 missing target in {scope}: sales-service-fee new mechanism must be appended")
    # G17
    for idx in candidate_paras("G17", lambda t: "销售服务费主要用于支付销售机构佣金" in t or "销售服务费的使用范围不包括" in t):
        if not has_target("G17", [idx]):
            issues.append(f"G17 missing target at p{idx}: sales-service-fee usage clause must be deleted")
    # G18
    for idx in candidate_paras("G18", lambda t: "不收取销售服务费，而" in t):
        if not has_target("G18", [idx]):
            issues.append(f"G18 missing target at p{idx}: old fee-difference reason phrase must be replaced")
    # G05
    for idx in candidate_paras("G05", lambda t: "调低赎回费率" in t and "基金份额类别" in t):
        if not has_target("G05", [idx]):
            issues.append(f"G05 missing target at p{idx}: class fee-adjustment clause must change")
    # G06
    for idx in candidate_paras("G06", lambda t: "不得互相转换" in t):
        if not has_target("G06", [idx]):
            issues.append(f"G06 missing target at p{idx}: class conversion restriction must be deleted")
    # G01/G03 append anchors
    for rule_id, section_word in (("G01", "释义"), ("G03", "基金的基本情况")):
        for idx in [
            p.index for p in doc.nonempty()
            if section_word in p.section_path
            and ("称为" in p.text or "将基金份额分为" in p.text)
            and "基金份额类别" in p.text
        ]:
            if not has_target(rule_id, [idx]):
                issues.append(f"{rule_id} missing append target at p{idx}: class definition direct-sale policy")
    # G22
    if floating is False and has_service is True and multi:
        for idx in candidate_paras("G22", lambda t: "全部剩余资产" in t):
            if not has_target("G22", [idx]):
                issues.append(f"G22 missing target at p{idx}: non-floating multi-class liquidation must add sales-service refund")
    # G19/G20
    if floating is True:
        for rule_id in ("G19", "G20"):
            for idx in candidate_paras(rule_id, lambda t: "全部剩余资产" in t):
                if not has_target(rule_id, [idx]):
                    issues.append(f"{rule_id} missing target at p{idx}: floating-fee liquidation clause")
    return issues


def build_case_result(
    *,
    case: dict[str, Any],
    doc: DocModel,
    raw: dict[str, Any],
    rule_map: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    issues: list[str] = []
    fund, fact_issues = normalize_facts(raw, doc)
    issues.extend(fact_issues)
    issues.extend(validate_evidence(fund, doc))
    targets, target_issues = normalize_targets(raw.get("targets"), doc, rule_map)
    issues.extend(target_issues)
    coverage, coverage_issues = normalize_coverage(raw.get("rule_coverage"), targets, doc)
    issues.extend(coverage_issues)
    targets, coverage, noop_notes = drop_noop_replacements(targets, coverage)
    issues.extend(noop_notes)
    targets, coverage, g13_notes = ensure_g13_targets(targets, coverage, doc, rule_map)
    issues.extend(g13_notes)
    for target in targets:
        issues.extend(validate_required_text(target, fund))
    issues.extend(audit_coverage(doc, coverage, targets))
    issues.extend(mandatory_checks(doc, fund, coverage, targets))
    satisfied, not_applicable, unknown, target_cov = derive_lists(coverage, targets)
    # uncertain: merge model uncertain with unknown coverage
    uncertain = raw.get("uncertain") if isinstance(raw.get("uncertain"), list) else []
    if doc.protection.get("protected"):
        # The protected document is deliberately out of the modification
        # denominator; keep all facts, but no write targets.
        for target in targets:
            target["confidence"] = "protected"
        targets = []
        coverage = []
        for rule_id in RULE_IDS:
            coverage.append({
                "rule_id": rule_id,
                "scope": "main",
                "status": "not_applicable",
                "paragraph_index": None,
                "reason": "DOCUMENT_PROTECTED: document protection metadata; no modification target by policy",
                "evidence_quote": None,
            })
        satisfied, not_applicable, unknown, target_cov = derive_lists(coverage, targets)
    result = {
        "case_id": case["case_id"],
        "group": case["group"],
        "file": case["file"],
        "relative": case.get("relative"),
        "sha256": case["sha256"],
        "bytes": case.get("bytes"),
        "stratum": case.get("stratum"),
        "document": {
            "paragraph_count": len(doc.paragraphs),
            "text_sha256": doc.text_sha256,
            "summary_start": doc.summary_start,
            "summary_headings": doc.summary_headings,
            "protection": doc.protection,
        },
        "fund": fund,
        "rule_coverage": coverage,
        "targets": targets,
        "satisfied": satisfied,
        "not_applicable": not_applicable,
        "unknown": unknown,
        "uncertain": uncertain,
        "protected": doc.protection if doc.protection.get("protected") else None,
        "excluded": None,
        "label_quality": {
            "issue_count": len(issues),
            "issues": issues[:80],
            "truncated_issues": max(0, len(issues) - 80),
        },
    }
    return result, issues


def usage_summary(usage: list[dict[str, Any]]) -> dict[str, Any]:
    by_phase: dict[str, dict[str, Any]] = {}
    models: set[str] = set()
    for event in usage:
        phase = event.get("phase", "unknown")
        bucket = by_phase.setdefault(phase, {
            "calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
            "total_tokens": 0, "latency_ms": 0, "errors": 0,
        })
        bucket["calls"] += 1
        for field_name in ("prompt_tokens", "completion_tokens", "total_tokens", "latency_ms"):
            value = event.get(field_name)
            if isinstance(value, int):
                bucket[field_name] += value
        if event.get("error"):
            bucket["errors"] += 1
        models.add(str(event.get("actual_model") or event.get("model") or ""))
    return {
        "calls": len(usage),
        "models": sorted(m for m in models if m),
        "by_phase": by_phase,
        "total_prompt_tokens": sum(
            e.get("prompt_tokens") or 0 for e in usage if isinstance(e.get("prompt_tokens"), int)
        ),
        "total_completion_tokens": sum(
            e.get("completion_tokens") or 0 for e in usage if isinstance(e.get("completion_tokens"), int)
        ),
        "total_tokens": sum(
            e.get("total_tokens") or 0 for e in usage if isinstance(e.get("total_tokens"), int)
        ),
    }


def run_case(
    *,
    case: dict[str, Any],
    selection: dict[str, Any],
    client: ModelClient,
    primary_model: str,
    review_model: str,
    guide_text: str,
    rule_map: dict[str, Any],
    review: bool,
    primary_temperature: float = 1.0,
    review_temperature: float = 0.0,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    case_id = case["case_id"]
    contract_path = ROOT / case.get("relative", "") if case.get("relative") else Path(selection["source_root"]) / case["file"]
    if not contract_path.exists():
        contract_path = Path(selection["source_root"]) / case["file"]
    actual_sha = sha256_file(contract_path)
    if actual_sha != case["sha256"]:
        raise RuntimeError(f"{case_id}: contract sha256 mismatch")
    doc = build_doc_model(contract_path)
    try:
        raw, _ = client.chat_json(
            model=primary_model,
            system=system_prompt(),
            user=primary_prompt(doc, guide_text),
            max_tokens=24000,
            phase="primary",
            case_id=case_id,
            retries=7,
            temperature=primary_temperature,
        )
    except RuntimeError as exc:
        if "truncated" not in str(exc):
            raise
        # A very long contract can exceed the model output cap. Split the rule
        # set into two passes and merge, rather than truncating the site list.
        raw_a, _ = client.chat_json(
            model=primary_model, system=system_prompt(),
            user=primary_prompt(doc, guide_text, RULE_IDS[:11]),
            max_tokens=24000, phase="primary_split_a", case_id=case_id,
            retries=6, temperature=primary_temperature,
        )
        raw_b, _ = client.chat_json(
            model=primary_model, system=system_prompt(),
            user=primary_prompt(doc, guide_text, RULE_IDS[11:]),
            max_tokens=24000, phase="primary_split_b", case_id=case_id,
            retries=6, temperature=primary_temperature,
        )
        raw = {
            "fund": raw_a.get("fund") or raw_b.get("fund") or {},
            "rule_coverage": (raw_a.get("rule_coverage") or []) + (raw_b.get("rule_coverage") or []),
            "targets": (raw_a.get("targets") or []) + (raw_b.get("targets") or []),
            "uncertain": (raw_a.get("uncertain") or []) + (raw_b.get("uncertain") or []),
        }
    result, issues = build_case_result(case=case, doc=doc, raw=raw, rule_map=rule_map)
    # One bounded repair pass if the model missed required coverage or
    # produced an invalid quote/location. This is not a truth search; it only
    # asks the same model to fix objective omissions against the same source.
    if issues:
        feedback = (
            "\n\n# 上一轮输出的客观问题\n"
            + "\n".join(f"- {item}" for item in issues[:80])
            + "\n请重新通读合同，输出完整 JSON，修正以上问题；不要减少已正确站点。\n"
        )
        raw2, _ = client.chat_json(
            model=primary_model,
            system=system_prompt(),
            user=primary_prompt(doc, guide_text) + feedback,
            max_tokens=24000,
            phase="primary_repair",
            case_id=case_id,
            retries=6,
            temperature=primary_temperature,
        )
        result2, issues2 = build_case_result(case=case, doc=doc, raw=raw2, rule_map=rule_map)
        if len(issues2) <= len(issues):
            result, issues = result2, issues2
    review_obj: dict[str, Any] = {
        "model": review_model if review else None,
        "status": "skipped",
        "findings": {"missing_targets": [], "incorrect_targets": [], "fact_issues": [], "status_issues": [], "uncertain": []},
    }
    if review and not result.get("protected"):
        try:
            findings, _ = client.chat_json(
                model=review_model,
                system=(
                    "你是独立基金合同标注复核人。只依据指引和合同原文复核，不参考引擎结果。"
                    "发现问题必须有逐字原文依据；不确定放 uncertain。只输出 JSON。"
                ),
                user=review_prompt(doc, guide_text, result),
                max_tokens=16000,
                phase="review",
                case_id=case_id,
                retries=6,
                temperature=review_temperature,
            )
            review_obj.update({
                "status": "completed",
                "verdict": findings.get("verdict"),
                "findings": {
                    "missing_targets": findings.get("missing_targets") or [],
                    "incorrect_targets": findings.get("incorrect_targets") or [],
                    "fact_issues": findings.get("fact_issues") or [],
                    "status_issues": findings.get("status_issues") or [],
                    "uncertain": findings.get("uncertain") or [],
                },
            })
            # Adjudicate only exact, in-scope missing-target findings.
            candidates: list[dict[str, Any]] = []
            for idx, finding in enumerate(review_obj["findings"]["missing_targets"], 1):
                if not isinstance(finding, dict):
                    continue
                para_idx = _as_int(finding.get("paragraph_index"))
                rule_id = str(finding.get("rule_id") or "").upper()
                old_text = str(finding.get("old_text") or "")
                if rule_id not in RULE_IDS or para_idx is None or not (0 <= para_idx < len(doc.paragraphs)):
                    continue
                if not old_text or find_span(doc.paragraphs[para_idx].text, old_text) is None:
                    continue
                required_text = str(finding.get("required_text") or "")
                if required_text and compact(required_text) == compact(old_text):
                    continue
                if not section_scope_ok(rule_id, doc.paragraphs[para_idx]):
                    continue
                candidates.append({**finding, "finding_id": f"F{idx}"})
            if candidates:
                decisions, _ = client.chat_json(
                    model=primary_model,
                    system=system_prompt(),
                    user=adjudication_prompt(doc, guide_text, {"missing_targets": candidates}),
                    max_tokens=12000,
                    phase="adjudicate",
                    case_id=case_id,
                    retries=6,
                    temperature=primary_temperature,
                )
                accepted: list[dict[str, Any]] = []
                rejected: list[dict[str, Any]] = []
                uncertain_decisions: list[dict[str, Any]] = []
                for decision in decisions.get("decisions") or []:
                    if not isinstance(decision, dict):
                        continue
                    if decision.get("decision") == "accept" and isinstance(decision.get("target"), dict):
                        accepted.append(decision["target"])
                    elif decision.get("decision") == "reject":
                        rejected.append(decision)
                    else:
                        uncertain_decisions.append(decision)
                if accepted:
                    raw_accept = {
                        "fund": result.get("fund"),
                        "rule_coverage": result.get("rule_coverage"),
                        "targets": result.get("targets", []) + accepted,
                        "uncertain": result.get("uncertain", []),
                    }
                    result3, issues3 = build_case_result(case=case, doc=doc, raw=raw_accept, rule_map=rule_map)
                    if len(issues3) <= len(issues):
                        result, issues = result3, issues3
                review_obj["adjudication"] = {
                    "accepted": len(accepted),
                    "rejected": rejected,
                    "uncertain": uncertain_decisions,
                }
        except RuntimeError as exc:
            review_obj.update({"status": "failed", "error": str(exc)[:240]})
    if issues:
        result["label_quality"]["issue_count"] = len(issues)
        result["label_quality"]["issues"] = issues[:80]
    result["review"] = review_obj
    result["usage"] = {
        "calls": sum(1 for e in client.usage if e.get("case_id") == case_id),
        "prompt_tokens": sum(
            e.get("prompt_tokens") or 0 for e in client.usage
            if e.get("case_id") == case_id and isinstance(e.get("prompt_tokens"), int)
        ),
        "completion_tokens": sum(
            e.get("completion_tokens") or 0 for e in client.usage
            if e.get("case_id") == case_id and isinstance(e.get("completion_tokens"), int)
        ),
    }
    return result, client.usage, review_obj


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", default=str(DEFAULT_SELECTION))
    parser.add_argument("--guide", default=str(DEFAULT_GUIDE))
    parser.add_argument("--rules", default=str(DEFAULT_RULES))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--review", action="store_true", default=True)
    parser.add_argument("--no-review", dest="review", action="store_false")
    parser.add_argument("--provider-env", default="")
    parser.add_argument("--primary-model", default="gpt-6-luna")
    parser.add_argument("--review-model", default="MiniMaxAI/MiniMax-M3")
    parser.add_argument("--primary-temperature", type=float, default=0.0)
    parser.add_argument("--review-temperature", type=float, default=0.0)
    parser.add_argument("--usage-out", default="")
    parser.add_argument("--batch-id", default="")
    parser.add_argument("--concurrency", type=int, default=1)
    args = parser.parse_args(argv)
    if args.concurrency < 1:
        raise SystemExit("--concurrency must be >= 1")

    selection_path = Path(args.selection)
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    guide_paras, guide_sha = load_guide(Path(args.guide))
    rules = json.loads(Path(args.rules).read_text(encoding="utf-8"))
    if rules.get("source_sha256") and rules["source_sha256"] != guide_sha:
        raise SystemExit("guide hash does not match guide rule map")
    rule_map = {g["rule_id"]: g for g in rules["groups"]}
    if set(rule_map) != set(RULE_IDS):
        raise SystemExit("guide rule ids are not G01..G22")
    guide_text = guide_prompt(rules, guide_paras)
    cases = selection.get("cases") or []
    if args.case:
        wanted = {c.upper() for c in args.case}
        cases = [c for c in cases if c["case_id"].upper() in wanted]
    elif not args.all:
        raise SystemExit("use --case ID (repeatable) or --all")
    if not cases:
        raise SystemExit("no cases selected")

    base_url, api_key, env_model = load_provider_env(args.provider_env)
    client = ModelClient(base_url, api_key)
    results: list[dict[str, Any]] = []
    all_usage: list[dict[str, Any]] = []
    def _run(case: dict[str, Any]):
        print(f"[label] {case['case_id']} {case['file']}", flush=True)
        result, _usage, _review = run_case(
            case=case,
            selection=selection,
            client=client,
            primary_model=args.primary_model,
            review_model=args.review_model,
            guide_text=guide_text,
            rule_map=rule_map,
            review=args.review,
            primary_temperature=args.primary_temperature,
            review_temperature=args.review_temperature,
        )
        print(
            f"[label] {case['case_id']} targets={len(result['targets'])} "
            f"issues={result['label_quality']['issue_count']} "
            f"review={result['review'].get('status')}",
            flush=True,
        )
        return result
    try:
        if args.concurrency == 1:
            for case in cases:
                results.append(_run(case))
        else:
            with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
                results.extend(executor.map(_run, cases))
    finally:
        client.close()
    all_usage = list(client.usage)
    batch_id = args.batch_id or selection.get("batch_id") or selection_path.stem
    output = {
        "schema": "fundlex-independent-labels-v1",
        "batch_id": batch_id,
        "frozen_at": now_iso(),
        "selection_sha256": sha256_file(selection_path),
        "selection": {
            "path": str(selection_path),
            "sha256": sha256_file(selection_path),
            "counts": selection.get("counts"),
            "frozen_at": selection.get("frozen_at"),
        },
        "guide": {
            "path": args.guide,
            "sha256": guide_sha,
            "rules_path": args.rules,
            "rules_sha256": sha256_file(Path(args.rules)),
        },
        "labeler": {
            "primary_model": args.primary_model,
            "review_model": args.review_model if args.review else None,
            "engine_model_env": env_model,
            "independence": (
                "Primary/review models are outside the engine model family and were given only "
                "the guide DOCX, guide rule map, frozen selection and original contracts; no engine "
                "prompts, reports, final/redline artifacts or historical P6 labels were read."
            ),
            "prompt_version": "independent-label-prompt-v1",
            "selection_sha256": sha256_file(selection_path),
            "source_hashes": {c["case_id"]: c["sha256"] for c in cases},
            "tool": "tools/evaluation/first_batch_label_20261028.py",
            "tool_sha256": sha256_file(Path(__file__)),
            "usage": usage_summary(all_usage),
        },
        "excluded": selection.get("excluded_from_modification_denominator") or [],
        "protected_cases": [
            {
                "case_id": c["case_id"],
                "file": c["file"],
                "policy": "DOCUMENT_PROTECTED",
                "reason": "document protection metadata; no modification target by policy; denominator retained",
            }
            for c in results if c.get("protected")
        ],
        "cases": results,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=1), encoding="utf-8")
    usage_path = Path(args.usage_out) if args.usage_out else out_path.with_suffix(".usage.json")
    usage_path.write_text(json.dumps({
        "batch_id": batch_id,
        "frozen_at": output["frozen_at"],
        "summary": output["labeler"]["usage"],
        "events": all_usage,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[label] wrote {out_path} sha256={sha256_file(out_path)}", flush=True)
    print(f"[label] wrote {usage_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
