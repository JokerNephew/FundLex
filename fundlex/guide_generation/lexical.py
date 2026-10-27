"""Portable lexical retrieval for the contract corpus.

No vector database is required for correctness.  The index is a compact
character-bigram inverted index with BM25-ish IDF weights; it is built from the
cached ClauseUnits of one corpus snapshot and discarded after the run.  Dense
retrieval is exposed as an optional extension point in :mod:`retrievers` and is
never allowed to suppress a lexical or semantic-sweep discovery.
"""
from __future__ import annotations

import math
import re
import zlib
from array import array
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from .models import ClauseUnit, PolicyRequirement, compact_for_match, normalize_space, unique

_CJK = re.compile(r"[\u3400-\u9fff]+")
_ASCII = re.compile(r"[A-Za-z0-9]+(?:[._%+/-][A-Za-z0-9]+)*")
_PERCENT = re.compile(r"\d+(?:\.\d+)?%")
_PUNCT = re.compile(r"[\s\u3000,，。;；:：、\.．!！?？\"'“”‘’（）()\[\]【】《》<>—\-_/]+")

DOMAIN_TERMS = (
    "基金合同", "招募说明书", "产品资料概要", "销售协议", "信息披露", "基金管理人",
    "基金托管人", "基金份额持有人", "投资者", "基金销售机构", "销售机构", "直销机构",
    "销售服务费", "认购费", "申购费", "赎回费", "认购", "申购", "赎回", "转换",
    "费率", "年费率", "收费", "收取", "计提", "支付", "基金财产", "基金资产",
    "基金资产净值", "份额类别", "A类", "B类", "C类", "D类", "E类", "I类",
    "持有期限", "持有期", "七日", "7日", "一年", "持续持有", "前端", "后端",
    "管理费", "托管费", "客户维护费", "尾随佣金", "促销", "公告", "备案",
    "计算", "计算方法", "公式", "净值", "金额", "比例", "上限", "不高于",
    "不得", "应当", "可以", "豁免", "免除", "不收", "免收", "减半", "优惠",
)

SECTION_HINTS = {
    "释义": ("释义", "定义", "含义", "词语"),
    "基金的基本情况": ("基本情况", "份额类别", "基金份额"),
    "申购与赎回": ("申购", "赎回", "转换", "价格", "费用", "费率"),
    "基金费用与税收": ("费用", "税收", "销售服务费", "管理费", "托管费"),
    "基金合同": ("基金合同", "变更", "终止", "清算"),
    "收益与分配": ("收益", "分配", "利润"),
    "信息披露": ("信息披露", "公告", "招募说明书"),
}


def _hash(token: str) -> int:
    return zlib.crc32(token.encode("utf-8")) & 0xFFFFFFFF


def tokenize(text: str) -> list[str]:
    """Character bigrams for Chinese plus ASCII/percentage tokens."""
    value = (text or "").lower()
    tokens: list[str] = []
    for match in _PERCENT.finditer(value):
        tokens.append(match.group(0))
    for match in _ASCII.finditer(value):
        token = match.group(0).strip("._-")
        if len(token) >= 2:
            tokens.append(token)
    for match in _CJK.finditer(value):
        run = match.group(0)
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[index:index + 2] for index in range(len(run) - 1))
    return tokens


@dataclass
class Query:
    requirement_id: str
    terms: list[str]
    phrases: list[str]
    section_hints: list[str]
    business_actions: list[str] = field(default_factory=list)
    intents: list[dict] = field(default_factory=list)

    @property
    def all_terms(self) -> list[str]:
        return unique(self.terms + self.business_actions + self.section_hints)


@dataclass
class RetrievalHit:
    clause_index: int
    clause_id: str
    contract_version_id: str
    score: float
    reasons: list[str]

    def to_dict(self) -> dict:
        return {"clause_index": self.clause_index, "clause_id": self.clause_id,
                "contract_version_id": self.contract_version_id,
                "score": round(self.score, 5), "reasons": self.reasons}


class LexicalIndex:
    def __init__(self, clauses: Sequence[ClauseUnit]):
        self.clauses = list(clauses)
        self.n = len(self.clauses)
        self.postings: dict[int, array] = defaultdict(lambda: array("I"))
        self.clause_tokens: list[tuple[int, ...]] = []
        self.contract_to_indices: dict[str, list[int]] = defaultdict(list)
        started: dict[int, int] = {}
        for index, clause in enumerate(self.clauses):
            token_ids = sorted({_hash(token) for token in tokenize(clause.text)})
            unique_ids: list[int] = []
            for token_id in token_ids:
                if token_id not in started:
                    started[token_id] = 0
                unique_ids.append(token_id)
            self.clause_tokens.append(tuple(unique_ids))
            for token_id in unique_ids:
                self.postings[token_id].append(index)
            self.contract_to_indices[clause.contract_version_id].append(index)
        self.df = {token_id: len(items) for token_id, items in self.postings.items()}
        self.avg_len = (sum(len(item) for item in self.clause_tokens) / self.n) if self.n else 0.0

    def _idf(self, token_id: int) -> float:
        df = self.df.get(token_id, 0)
        return math.log((self.n + 1) / (df + 0.5)) if df else 0.0

    def search(self, query: Query, *, top_k: int = 240, per_contract: int = 4,
               max_candidates: int = 1600) -> list[RetrievalHit]:
        if not self.clauses:
            return []
        scores: dict[int, float] = defaultdict(float)
        reasons: dict[int, set[str]] = defaultdict(set)
        for term in query.all_terms:
            if not term:
                continue
            # Generic fee vocabulary is useful for breadth but must not drown
            # the requirement's own subject/object terms.
            weight = 0.35 if term in DOMAIN_TERMS else 2.0
            if term in query.business_actions:
                weight = max(weight, 2.5)
            for token in tokenize(term):
                token_id = _hash(token)
                if token_id not in self.postings:
                    continue
                idf = self._idf(token_id)
                for index in self.postings[token_id]:
                    scores[index] += idf * weight
                    reasons[index].add(f"term:{term}")
        if not scores:
            # Fall back to a deterministic phrase scan so a rare exact term is
            # never lost merely because it was not in the bigram index.
            compact_terms = [compact_for_match(term) for term in query.all_terms if term]
            for index, clause in enumerate(self.clauses):
                text = compact_for_match(clause.text)
                if any(term and term in text for term in compact_terms):
                    scores[index] = 1.0
                    reasons[index].add("fallback:phrase")
        for index in list(scores):
            text = self.clauses[index].text
            for phrase in query.phrases:
                if phrase and compact_for_match(phrase) in compact_for_match(text):
                    scores[index] += 8.0
                    reasons[index].add(f"phrase:{phrase}")
            path = " ".join(self.clauses[index].section_path)
            for hint in query.section_hints:
                if hint and (hint in path or any(part in path for part in SECTION_HINTS.get(hint, ()))):
                    scores[index] += 4.0
                    reasons[index].add(f"section:{hint}")
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        selected: list[int] = []
        seen: set[int] = set()
        # Global top-k.
        for index, _score in ranked[:top_k]:
            if index not in seen:
                selected.append(index)
                seen.add(index)
        # Top per contract keeps a single large contract from dominating recall.
        per: dict[str, int] = defaultdict(int)
        for index, _score in ranked:
            contract = self.clauses[index].contract_version_id
            if per[contract] >= per_contract:
                continue
            per[contract] += 1
            if index not in seen:
                selected.append(index)
                seen.add(index)
            if len(selected) >= max_candidates:
                break
        return [RetrievalHit(index, self.clauses[index].clause_id,
                             self.clauses[index].contract_version_id, scores[index],
                             sorted(reasons[index])[:12]) for index in selected]


def deterministic_query(requirement: PolicyRequirement) -> Query:
    text = " ".join(filter(None, [
        requirement.requirement, requirement.subject, requirement.object,
        " ".join(requirement.conditions), " ".join(requirement.exceptions),
        " ".join(requirement.candidate_contract_domains),
    ]))
    terms = unique(list(DOMAIN_TERMS) + [
        requirement.subject, requirement.object,
        *requirement.candidate_contract_domains,
        *requirement.conditions, *requirement.exceptions,
    ])
    # Remove very generic terms only from the scoring list, never from evidence
    # coverage.  They remain useful as section hints.
    section_hints = [item for item in requirement.candidate_contract_domains if item]
    for hint, aliases in SECTION_HINTS.items():
        if any(alias in text for alias in aliases):
            section_hints.extend([hint, *aliases[:2]])
    phrases = unique([requirement.object, requirement.subject,
                      *[item for item in requirement.conditions if len(item) >= 4][:8]])
    return Query(requirement_id=requirement.requirement_id, terms=terms,
                 phrases=phrases, section_hints=section_hints)


def query_from_intents(requirement: PolicyRequirement, intents: Iterable[dict]) -> Query:
    base = deterministic_query(requirement)
    terms = list(base.terms)
    phrases = list(base.phrases)
    hints = list(base.section_hints)
    actions: list[str] = []
    raw_intents: list[dict] = []
    for intent in intents:
        if not isinstance(intent, dict):
            continue
        raw_intents.append(intent)
        terms.extend(str(item) for item in intent.get("terms") or [] if str(item).strip())
        phrases.extend(str(item) for item in intent.get("phrases") or [] if str(item).strip())
        hints.extend(str(item) for item in intent.get("section_hints") or [] if str(item).strip())
        actions.extend(str(item) for item in intent.get("business_actions") or [] if str(item).strip())
    return Query(requirement_id=requirement.requirement_id, terms=unique(terms),
                 phrases=unique(phrases), section_hints=unique(hints),
                 business_actions=unique(actions), intents=raw_intents)
