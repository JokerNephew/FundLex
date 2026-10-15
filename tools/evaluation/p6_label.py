"""Independent labeler for the P6 real-revision evaluation.

This tool reads ONLY the frozen sample manifest, the guide and the original contracts.
It never reads engine output, plans, reports or predictions, so the labels it writes are
an independent gold that can be frozen before any real run.

For every case it decides, from the contract text alone:

* the fund type and whether the guide's qualification excludes it (etf / money_market /
  interbank_cd);
* the current share classes and their fee rules, hence ``class_count``, ``has_service_fee``
  and ``is_floating_fee``;
* which guide rules therefore apply, with the exact obligation (append / replace / delete)
  and the required resulting text.

The fact derivation here is deliberately a different implementation from the delivery
engine's model-assisted ``extract_facts``: it is keyword/section based, deterministic and
auditable. Any disagreement between these labels and the engine is reported as a fact or
target defect, never silently reconciled.

Run::

    .venv/bin/python -X utf8 -m tools.evaluation.p6_label --selection var/recall-first-evaluation/p6/selection.json \
        --output var/recall-first-evaluation/p6/labels.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
Q = lambda name: "{" + W + "}" + name

COMPACT = re.compile(r"[\s\u3000]")

# Qualification: the guide applies to ordinary open-end funds. Index ETFs, money-market
# funds and interbank CD funds are out of scope (same vocabulary as the engine default).
EXCLUDED_TYPES = ("etf", "money_market", "interbank_cd")


def compact(text: str) -> str:
    return COMPACT.sub("", text or "")


def paragraphs_of(path: Path) -> list[str]:
    with ZipFile(path) as package:
        root = etree.fromstring(package.read("word/document.xml"),
                                parser=etree.XMLParser(resolve_entities=False, no_network=True))
    body = root.find(Q("body"))
    return ["".join(node.text or "" for node in paragraph.iter(Q("t")))
            for paragraph in body.iter(Q("p"))]


def category_wording(paragraphs: list[str]) -> str:
    """The fund category as stated in the 基金的基本情况 section.

    The heading "基金的类别" is immediately followed by the category text, either in the
    same paragraph (most contracts) or in the next one. Searching only a short window keeps
    boilerplate like "货币市场工具" in the investment scope from deciding the fund type.
    """
    for index, paragraph in enumerate(paragraphs):
        flat = compact(paragraph)
        if "基金的类别" not in flat or len(flat) > 60:
            continue
        tail = flat.split("基金的类别", 1)[1]
        window = tail + compact(paragraphs[index + 1] if index + 1 < len(paragraphs) else "")
        if window[:2].isdigit() or window.startswith("、") or window.startswith("："):
            window = window.lstrip("0123456789、：")
        if window:
            return window[:200]
    # Fallback: the definition clause declares the fund's own type.
    match = re.search(r"本基金(?:为|是)([^。；\n]{0,30}?(?:证券投资基金|基金中基金|货币市场基金))", compact("".join(paragraphs)))
    return match.group(1) if match else ""


def fund_type_of(paragraphs: list[str]) -> str:
    wording = category_wording(paragraphs)
    if re.search(r"交易型开放式指数|ETF", wording):
        return "etf"
    if "同业存单" in wording:
        return "interbank_cd"
    if "货币市场" in wording or "货币基金" in wording:
        return "money_market"
    if "债券型" in wording:
        return "bond"
    if "股票型" in wording:
        return "equity"
    if "混合型" in wording or "基金中基金" in wording or "FOF" in wording:
        return "hybrid"
    return "other"


def current_classes(paragraphs: list[str]) -> list[dict]:
    """Share classes in force, with the fee rule each class is described by.

    The 释义 clause "基金份额类别：本基金将基金份额分为A类和C类…" is authoritative. The
    sentence after it lists the fee rule per class, for example
    "在投资者申购A类及D类基金份额时收取申购费用，不计提销售服务费；在投资者申购C类基金份额时
    不收取申购费用，而从本类别基金资产中计提销售服务费". Each clause is read on its own so
    one class's wording never leaks into another's fee flags.
    """
    joined = compact("\n".join(paragraphs))
    letters: list[str] = []
    # The division clause is authoritative: "本基金将基金份额分为A类、C类和D类三种不同的类别" or,
    # when the sentence straddles a paragraph break, "…将基金份额分为A" / "类基金份额和Y类基金份额。".
    # Read the whole sentence and pick up every "<letter>类基金份额" it names.
    for match in re.finditer(r"将基金份额分为([^。；]{0,80})", joined):
        for token in re.findall(r"([A-Z])类基金份额", match.group(1)):
            if token not in letters:
                letters.append(token)
        if not letters:
            for token in re.findall(r"([A-Z])类", match.group(1)):
                if token not in letters:
                    letters.append(token)
    if not letters:
        # Definition-by-glossary wording: "A类基金份额或A类份额：指投资人申购时收取申购费用…".
        for match in re.finditer(r"([A-Z])类基金份额或[A-Z]类份额：指", joined):
            token = match.group(1)
            if token not in letters:
                letters.append(token)
    if not letters:
        # Some contracts name the classes only via the code clause.
        for match in re.finditer(r"本基金([A-Z]类基金份额(?:[、，,和及][A-Z]类基金份额)*)(?:分别设置代码|将分别计算)",
                                 joined):
            for token in re.findall(r"([A-Z])类基金份额", match.group(1)):
                if token not in letters:
                    letters.append(token)
    if not letters:
        for match in re.finditer(r"称为([A-Z])类基金份额", joined):
            token = match.group(1)
            if token not in letters:
                letters.append(token)
    # Definition-by-glossary wording is authoritative when present:
    # "A类基金份额或A类份额：指投资人申购时收取申购费用，但不从本类别资产中计提销售服务费…".
    glossary = re.findall(r"([A-Z])类基金份额或[A-Z]类份额：指", joined)
    if glossary:
        letters = []
        for token in glossary:
            if token not in letters:
                letters.append(token)
    if not letters:
        # Single-class contracts never divide the fund, so no named class exists. The
        # guide still applies with class_count = 1 and no service fee.
        return [{"name": "基金份额", "letter": "", "subscription_fee": True,
                 "service_fee": False}]

    classes: list[dict] = []
    for letter in letters:
        service = False
        subscription = False
        marker = f"{letter}类" if letter else ""
        # Priority 1: the dedicated clause "本基金A类基金份额和D类基金份额不收取销售服务费，C类
        # 基金份额的销售服务费按…计提" names each side explicitly.
        for match in re.finditer(
                r"([A-Z](?:类基金份额|类份额)?(?:[、，,和及][A-Z](?:类基金份额|类份额)?)*)"
                r"(?:类)?(?:基金)?份额(?:不收取|不计提|不.{0,14}(?:计提|收取))销售服务费", joined):
            if letter in re.findall(r"([A-Z])类?", match.group(1)):
                service = False
                break
        else:
            for match in re.finditer(
                    r"([A-Z](?:类基金份额|类份额)?(?:[、，,和及][A-Z](?:类基金份额|类份额)?)*)"
                    r"(?:类)?(?:基金)?份额?(?:的)?销售服务费(?:年费率为|按)", joined):
                if letter in re.findall(r"([A-Z])类?", match.group(1)):
                    service = True
                    break
            else:
                # Priority 2: the definition sentence, split on the semicolon so one class's
                # wording never sets another class's flag.
                for clause in re.split(r"[；;]", joined):
                    if marker and marker not in clause:
                        continue
                    if re.search(r"(?:计提|收取)销售服务费", clause) and \
                            not re.search(r"不.{0,14}(?:计提|收取)销售服务费", clause):
                        service = True
                # Priority 3: the explicit "X类份额的销售服务费年费率为…" clause.
                for match in re.finditer(r"([A-Z](?:类)?(?:[、，,和及][A-Z](?:类)?)*)份额?(?:的)?销售服务费(?:年费率为)",
                                         joined):
                    if letter in re.findall(r"([A-Z])类?", match.group(1)):
                        service = True
        for clause in re.split(r"[；;。\n]", joined):
            if marker and marker not in clause:
                continue
            if re.search(r"收取(?:认购、申购|认购|申购)费", clause) and \
                    not re.search(r"不收取(?:认购、申购|认购|申购)费", clause):
                subscription = True
                break
        classes.append({"name": f"{letter}类基金份额" if letter else "基金份额",
                        "letter": letter, "subscription_fee": subscription,
                        "service_fee": service})
    return classes


def floating_fee(text: str) -> bool:
    return bool(re.search(r"浮动管理费|浮动费率|或有管理费|超额管理费|业绩报酬", text))


def matches_condition(condition: dict, facts: dict) -> bool:
    kind = (condition or {}).get("kind") or "none"
    value = (condition or {}).get("value")
    if kind == "none":
        return True
    if kind == "class_count":
        if value == 1:
            return facts["class_count"] == 1
        return facts["class_count"] > 1
    if kind == "has_service_fee":
        return bool(value) == bool(facts["has_service_fee"])
    if kind == "is_floating_fee":
        return bool(value) == bool(facts["is_floating_fee"])
    if kind == "compound":
        return all(matches_condition(item, facts) for item in value or [])
    return False


def locate(text: str, needle: str) -> dict | None:
    """First literal (whitespace-insensitive) occurrence of ``needle`` in the contract."""
    if not needle:
        return None
    target = compact(needle)
    if not target:
        return None
    stripped = compact(text)
    index = stripped.find(target)
    if index < 0:
        return None
    return {"needle": needle, "compact_start": index,
            "compact_end": index + len(target)}


# Semantic intents per rule. Contract wording differs from the guide's literal wording, so
# each rule also declares the phrase that identifies its clause. These patterns come from
# the guide requirement text and the observed contract variety, never from engine output.
SEMANTIC_PATTERNS: dict[str, list[str]] = {
    "G06": [r"不同基金份额类别之间不得互相转换", r"份额类别之间不得.{0,4}转换"],
    "G07": [r"本基金的申购费率由基金管理人决定，并在招募说明书中列示"],
    "G08": [r"本基金的申购费率由基金管理人决定，并在招募说明书中列示"],
    "G09": [r"赎回金额为按实际确认的有效赎回份额乘以当日.{0,8}的?基金份额净值并扣除.{0,2}相应的费用"],
    "G10": [r"申购费用由投资人承担，不列入基金财产"],
    "G11": [r"申购费用由投资人承担，不列入基金财产", r"A类基金份额的申购费用由投资人承担"],
    "G12": [r"赎回费用由赎回基金份额的基金份额持有人承担，在基金份额持有人赎回基金份额时收取"],
    "G13": [r"对持续持有期少于7日的投资者收取.{0,6}1\.?5?0?%的赎回费", r"持续持有期少于7日的投资者收取.{0,6}赎回费"],
    "G14": [r"可以适当调低.{0,24}(?:申购费率|赎回费率)", r"适当调低.{0,24}费率"],
    "G15": [r"销售服务费每日(计提|计算)", r"销售服务费每日.{0,8}按月支付"],
    "G17": [r"销售服务费主要用于支付销售机构佣金"],
    "G18": [r"由于本基金A类基金份额(?:和[A-Z]类基金份额)*不收取销售服务费，而C类基金份额收取销售服务费",
            r"不收取销售服务费，而C类基金份额收取销售服务费"],
    "G22": [r"依据基金财产清算的分配方案，将基金财产清算后的全部剩余资产扣除基金财产清算费用"],
}


def semantic_locate(text: str, rule_id: str) -> dict | None:
    stripped = compact(text)
    for pattern in SEMANTIC_PATTERNS.get(rule_id, []):
        match = re.search(compact(pattern), stripped)
        if match:
            return {"needle": stripped[match.start():match.end()],
                    "compact_start": match.start(), "compact_end": match.end()}
    return None


def rule_not_applicable(group: dict, operations: list[dict], facts: dict) -> bool:
    """Reserved for a future label-policy revision; not used by the frozen labeler.

    The guide conditions already decide applicability (for example G05 carries
    ``has_service_fee`` on both branches), so the labels follow the guide's own conditions
    rather than re-deriving the engine's out-of-scope policy. Where the engine and the
    guide conditions disagree, the disagreement is reported, not silently reconciled.
    """
    return False


def label_case(case: dict, words_root: Path, guide: dict) -> dict:
    path = words_root / case["file"]
    paragraphs = paragraphs_of(path)
    text = "\n".join(paragraphs)
    fund_type = fund_type_of(paragraphs)
    classes = current_classes(paragraphs)
    facts = {
        "fund_type": fund_type,
        "excluded": fund_type in EXCLUDED_TYPES,
        "class_count": len(classes),
        "classes": classes,
        "has_service_fee": any(item["service_fee"] for item in classes),
        "is_floating_fee": floating_fee(text),
    }

    targets: list[dict] = []
    skipped: list[dict] = []
    not_applicable: list[dict] = []
    if not facts["excluded"]:
        for group in guide["groups"]:
            rule_id = group["rule_id"]
            # One obligation per rule per contract. Gather every applicable operation and
            # every wording variant, then pick the first one whose source text really is in
            # the contract. An operation whose wording is absent is either already
            # satisfied (delete/replace) or unconfirmed, and never becomes a second target.
            applicable = [operation for operation in group["operations"]
                          if operation["op"] != "noop"
                          and matches_condition(operation.get("condition") or {}, facts)]
            if not applicable:
                continue
            # An append carries no source wording; it always applies when its condition
            # holds and its anchor clause exists.
            if all(operation["op"] == "append" for operation in applicable):
                operation = applicable[0]
                targets.append({
                    "target_id": f"{case['case_id']}:{rule_id}",
                    "rule_id": rule_id, "section": group["section_hint"], "op": "append",
                    "condition": operation.get("condition"),
                    "anchor": None, "required_text": operation.get("new_text"),
                    "requirement": group["requirement"], "located": True, "confirmed": True,
                })
                continue
            chosen = None
            for operation in applicable:
                candidates = [operation.get("old_text")] + list(group.get("old_text_variants") or [])
                for candidate in candidates:
                    found = locate(text, candidate or "")
                    if found is not None:
                        chosen = (operation, candidate, found)
                        break
                if chosen:
                    break
            if chosen is None:
                found = semantic_locate(text, rule_id)
                if found is not None:
                    chosen = (applicable[0], found["needle"], found)
            if chosen is None:
                # A delete/replace obligation whose source clause is absent from the
                # contract is already satisfied: there is nothing to change. It is not a
                # target and not an unconfirmed label.
                not_applicable.append({
                    "rule_id": rule_id, "op": applicable[0]["op"],
                    "reason": "source_clause_absent",
                    "condition": applicable[0].get("condition"),
                })
                continue
            operation, candidate, found = chosen
            targets.append({
                "target_id": f"{case['case_id']}:{rule_id}",
                "rule_id": rule_id, "section": group["section_hint"], "op": operation["op"],
                "condition": operation.get("condition"),
                "anchor": candidate, "required_text": operation.get("new_text"),
                "requirement": group["requirement"], "located": True, "confirmed": True,
                "old_text": candidate,
                "compact_start": found["compact_start"], "compact_end": found["compact_end"],
            })
    else:
        skipped.append({"rule_id": "ALL", "reason": "excluded_by_fund_type",
                        "fund_type": fund_type})

    return {
        "case_id": case["case_id"], "group": case["group"], "file": case["file"],
        "sha256": case["sha256"], "paragraphs": len(paragraphs),
        "facts": facts,
        "targets": targets,
        "skipped": skipped,
        "not_applicable": not_applicable,
        "target_count": len([t for t in targets if t.get("confirmed")]),
        "unconfirmed_count": len([t for t in targets if not t.get("confirmed")]),
        "conditional_count": len([t for t in targets if t.get("confirmed")
                                  and (t.get("condition") or {}).get("kind") != "none"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", default="var/recall-first-evaluation/p6/selection.json")
    parser.add_argument("--guide", default="guides/builtin_guide_v1.json")
    parser.add_argument("--data-root", default="/home/opencode/data")
    parser.add_argument("--output", default="var/recall-first-evaluation/p6/labels.json")
    args = parser.parse_args()

    selection = json.loads(Path(args.selection).read_text(encoding="utf-8"))
    guide = json.loads(Path(args.guide).read_text(encoding="utf-8"))
    guide_hash = hashlib.sha256(Path(args.guide).read_bytes()).hexdigest()
    selection_hash = hashlib.sha256(Path(args.selection).read_bytes()).hexdigest()
    words_root = Path(args.data_root) / "funds_word"

    labels = [label_case(case, words_root, guide) for case in selection["cases"]]
    payload = {
        "schema": "fundlex-p6-labels-v1",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "blind_to_engine": True,
        "selection_sha256": selection_hash,
        "guide_sha256": guide_hash,
        "engine": selection.get("engine"),
        "cases": labels,
        "totals": {
            "cases": len(labels),
            "targets": sum(row["target_count"] for row in labels),
            "unconfirmed": sum(row["unconfirmed_count"] for row in labels),
            "editable_cases": sum(1 for row in labels if row["target_count"] > 0),
            "excluded_cases": sum(1 for row in labels if row["facts"]["excluded"]),
            "conditional_targets": sum(row["conditional_count"] for row in labels),
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for row in labels:
        print(row["case_id"], row["group"], "type=", row["facts"]["fund_type"],
              "classes=", row["facts"]["class_count"], "service=", row["facts"]["has_service_fee"],
              "float=", row["facts"]["is_floating_fee"], "targets=", row["target_count"],
              "unconf=", row["unconfirmed_count"], "cond=", row["conditional_count"])
    print(json.dumps(payload["totals"], ensure_ascii=False))
    print("labels sha256:", hashlib.sha256(output.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
