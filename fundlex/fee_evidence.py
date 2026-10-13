"""Conservative verification of class fee facts in exact contract quotations."""
from __future__ import annotations

import re
from collections.abc import Iterable

_CLASS_GROUP = re.compile(r"[A-ZＡ-Ｚ](?:类)?(?:(?:及|和|与|、|/)[A-ZＡ-Ｚ](?:类)?)*类(?:基金)?份额|[A-ZＡ-Ｚ](?:类)?(?:(?:及|和|与|、|/)[A-ZＡ-Ｚ](?:类)?)*类")
_SPECIAL = re.compile(r"直销|持续持有|优惠|特定投资|养老金|机构投资者|个人投资者|网上|电子交易|通过.*销售机构|其他投资者|特定渠道")
_UNCERTAIN = re.compile(r"是否|可能|可以|有权|应当|不得|不应|可(?:收取|计提)|如果|若")


def _shared_respective_fee(block: str, field: str) -> bool:
    """Allow only one identical service-fee predicate for a joint subject."""
    if field != "sales_service_fee" or block.count("分别") != 1:
        return False
    if len(set(re.findall(r"[A-ZＡ-Ｚ]", block))) < 2:
        return False
    if re.search(r"申购费|认购费|管理费|赎回费|\d|[%％]", block):
        return False
    if block.count("销售服务费") != 1:
        return False
    # The predicate must immediately follow the explicit joint subject.
    # Extra narrative/negation before 分别 cannot be silently discarded.
    subject = block.split("分别", 1)[0]
    connectors = _CLASS_GROUP.sub("", subject)
    if not re.fullmatch(r"(?:及|和|与|、)*", connectors):
        return False
    return bool(re.search(r"分别从本类别(?:份额)?基金资产中计提销售服务费(?:用)?[，,]?$", block))


def _polarities(text: str, field: str) -> set[bool]:
    fee = r"(?:认购[、/和及])?申购(?:费用|费)" if field == "subscription_fee" else r"销售服务费(?:用)?"
    prefix = r"(?:不收取|不再收取|免收|不(?:从(?:本(?:类别|类)?(?:基金)?资产|基金资产)中)?计提)"
    negative = bool(re.search(prefix + fee, text))
    rest = re.sub(prefix + fee, "", text)
    positive = bool(re.search(r"(?:收取|计提)" + fee, rest))
    for match in re.finditer(fee + r"(?:年费率|率|年|按|的|为|是|：|:|以)*(\d+(?:\.\d+)?)[%％]", text):
        negative |= float(match.group(1)) == 0
        positive |= float(match.group(1)) > 0
    # A fee's own explicit NAV calculation is evidence. The narrow grammar
    # cannot absorb another fee name or an intervening negative predicate.
    nav_rate = fee + r"按前一日(?:[A-ZＡ-Ｚ]类基金份额|本类别基金份额|本类别基金|基金)?资产净值的(\d+(?:\.\d+)?)[%％]年费率计提"
    for match in re.finditer(nav_rate, text):
        negative |= float(match.group(1)) == 0
        positive |= float(match.group(1)) > 0
    return ({True} if positive else set()) | ({False} if negative else set())


def fee_value(quote: str, field: str, name: str, *, single_bound: bool = False) -> bool | None:
    """Return an explicit default fee polarity, or None for missing/ambiguous facts.

    Subjects may govern subsequent comma clauses, but never another sentence
    or another class's predicate. Special investor/channel clauses cannot
    establish the default fee. This function never constructs an evidence quote.
    """
    if field not in {"subscription_fee", "sales_service_fee"} or not isinstance(quote, str):
        return None
    text = re.sub(r"[^\S\n]+", "", quote)
    values: set[bool] = set()
    for sentence in re.split(r"[。；;！!？?\n]", text):
        if not sentence:
            continue
        subjects = list(_CLASS_GROUP.finditer(sentence))
        if not subjects:
            if single_bound and "本基金" in sentence:
                blocks = [sentence]
            else:
                continue
        else:
            blocks = []
            groups: list[tuple[int, int, set[str]]] = []
            for subject in subjects:
                names = set(re.findall(r"[A-ZＡ-Ｚ]", subject.group()))
                if groups:
                    start, end, previous_names = groups[-1]
                    bridge = sentence[end:subject.start()]
                    if names == previous_names or re.fullmatch(r"(?:及|和|与|、)", bridge):
                        groups[-1] = (start, subject.end(), previous_names | names)
                        continue
                groups.append((subject.start(), subject.end(), names))
            for index, (start, _, names) in enumerate(groups):
                if name not in names or name == "__single__":
                    continue
                end = groups[index + 1][0] if index + 1 < len(groups) else len(sentence)
                # In a trailing definition, the predicate precedes its subject.
                if len(subjects) == 1 and re.search(r"称为$|称作$", sentence[:start]):
                    blocks.append(sentence)
                else:
                    prefix = sentence[:start]
                    if _SPECIAL.search(prefix):
                        continue
                    blocks.append(sentence[start:end])
        for block in blocks:
            if "分别" in block and not _shared_respective_fee(block, field):
                continue
            special = False
            for clause in re.split(r"[，,]", block):
                special |= bool(_SPECIAL.search(clause))
                if special or _UNCERTAIN.search(clause):
                    continue
                values.update(_polarities(clause, field))
    return next(iter(values)) if len(values) == 1 else None


def verify_fee_evidence(quote: str, field: str, name: str, source_texts: Iterable[str], *, single_bound: bool = False) -> bool | None:
    """Require a nonempty, exact contiguous source quotation before verification."""
    if not isinstance(quote, str) or not quote or not any(quote in source for source in source_texts):
        return None
    return fee_value(quote, field, name, single_bound=single_bound)
