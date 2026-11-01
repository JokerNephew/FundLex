#!/usr/bin/env python3
"""W3 接管线独立重验脚本（第二波标签冻结物）

目的：主线裁决 W2 停滞后，由 W3 对 W2 交付的冻结标签做**独立双盲重验**。
与 W2 自建的 verify_second_batch_labels_20261031.py 无代码共享——本脚本全部
校验逻辑按 schema 口径文档（docs/evidence/labels-schema-second-batch-20261031-v1.md）
与总攻令要求独立重写。

检查域（总攻令测试要求：格式 / 必填字段 / 分母一致性）：
  A. 格式与必填字段：顶层 envelope、每案必填字段、rule_coverage/targets 子结构、
     op/status 白名单、provenance 白名单。
  B. 选样对齐：labels 与 selection-second-batch-20261031.json 逐案
     case_id/group/file/relative/sha256/bytes 一致；100 齐全、dev75/holdout25。
  C. 源文件真实性：每案 funds_word 源 DOCX 存在、字节 sha256 与 manifest 一致。
  D. 原文证据对照：rule_coverage.evidence_quote 与 targets.old_text/source_quote/
     anchor_quote 经空白规整后必须真实出现在源 DOCX 全文；paragraph_index 不越界。
  E. 保护/边界口径：保护扫描（w:documentProtection）与 labels document.protection
     一致；boundary 工件内部账目=100；货币市场 3 案 eligible=False 且零 target；
     references/ 路径不出现（fee-rule-v2 黄金对不混入分母——总攻令硬条款）。
  F. 标注模型避嫌：labeler 模型非引擎家族（kimi-k3），不得读引擎产物。
  G. 总账一致性：targets=1254、coverage=4350、有目标案=84、review=completed 100、
     verification 自述 totals 与本脚本实测重算一致。

用法：
  python w3_reverify_second_batch_labels_20261101.py --batch 1  # 1..5（每批 20 案）
  python w3_reverify_second_batch_labels_20261101.py --batch all # 全量+总账

输出：JSON 写 docs/evidence/w3-reverify/batch-<n>.json；全量另写 summary.json。
退出码：0 = 该批 problems=0；1 = 有 problem。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LABELS = ROOT / "docs/evidence/labels-second-batch-20261031-v1.json"
SELECTION = ROOT / "docs/evidence/selection-second-batch-20261031.json"
BOUNDARY = ROOT / "docs/evidence/boundary-second-batch-20261031.json"
VERIFICATION = ROOT / "docs/evidence/labels-second-batch-20261031-v1-verification.json"
OUTDIR = ROOT / "docs/evidence/w3-reverify"
SOURCE_ROOT = Path("/home/opencode/fundlex/funds_word")

EXPECTED_LABELS_SHA = "423c6944687a6006d493d3f8dff4b4cb32593cc6acc26c2e2b3fb423622a88f5"
EXPECTED_SELECTION_SHA = "32b36f02a9c6cafebee7a73fcda0791c707ac62d07fe67bb57e91daafc6187d9"

# Label schema 沿用第一波 v2（同 envelope 名称，见 schema 口径文档 §2）
EXPECTED_SCHEMA = "fundlex-independent-labels-v1"
# prose-first evidence 引文允许跨段拼接/省略夹缝段——校验拆成分句原子片段
FRAG_SPLIT = re.compile(r"[。；;！!？?：:\n]")

OPS = {"delete", "append", "replace"}
STATUSES = {"target", "satisfied", "not_applicable", "unknown"}
PROVENANCE = {"model", "guide_deterministic_completion"}
CASE_REQUIRED = [
    "case_id", "group", "file", "relative", "sha256", "bytes", "stratum",
    "document", "fund", "rule_coverage", "targets", "satisfied",
    "not_applicable", "unknown", "uncertain", "label_quality", "review",
]
TARGET_REQUIRED = ["target_id", "rule_id", "op", "scope"]
RC_REQUIRED = ["rule_id", "scope", "status"]

_ws = re.compile(r"\s+")


def norm(s: str | None) -> str:
    return _ws.sub("", s or "")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


import docx as _docx_lib  # python-docx：labels 的 paragraph 惯例同口径


def docx_paragraphs(path: Path) -> list[str]:
    """python-docx 顶层段落（labels 索引/计数惯例的出处）。"""
    return [p.text for p in _docx_lib.Document(str(path)).paragraphs]
def docx_full_text(path: Path) -> str:
    """正文全部 w:p 正则拼接（含 python-docx 顶层列表之外的 sdt/文本框），
    引文片段查真用全集，宁可超集不可漏。"""
    import xml.etree.ElementTree as ET

    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    pieces = []
    for p in root.iter(w + "p"):
        texts = [t.text or "" for t in p.iter(w + "t")]
        pieces.append("".join(texts))
    return norm("".join(pieces))


def fragments(quote: str) -> list[str]:
    # 省略号属标注方明示省略写法：按省略号再切分，两段各自独立查真
    segs = re.split(r"…+|\.{3,}", quote or "")
    out: list[str] = []
    for seg in segs:
        for piece in FRAG_SPLIT.split(seg):
            f = norm(piece).strip("，,、" + "…")
            if len(f) >= 10:
                out.append(f)
    return out


_PUNCT = re.compile(r"[，。、；：,.;:!?！？「」『』“”\"'‘’（）()\[\]【】<>《》\-—/·]")


def strip_punct(s: str) -> str:
    return _PUNCT.sub("", s)


def fragment_class(f: str, full_text: str, full_nopunct: str) -> str:
    """verbatim=逐字在场 / punct=仅标点差异 / missing=内容级不在场"""
    if f in full_text:
        return "verbatim"
    if strip_punct(f) in full_nopunct:
        return "punct"
    return "missing"


def docx_protection(path: Path) -> bool:
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if name == "word/settings.xml":
                return b"documentProtection" in z.read(name)
    return False


def check_case(case: dict, sel_case: dict, problems: list, warnings: list, stats: dict) -> None:
    cid = case.get("case_id", "<?>")
    # A: required fields
    for k in CASE_REQUIRED:
        if k not in case:
            problems.append(f"{cid}: missing field {k}")
    # B: selection alignment
    for k in ("case_id", "group", "file", "relative", "sha256", "bytes"):
        if case.get(k) != sel_case.get(k):
            problems.append(f"{cid}: selection mismatch on {k}: {case.get(k)!r} vs {sel_case.get(k)!r}")
    if case.get("group") not in ("dev", "holdout"):
        problems.append(f"{cid}: bad group {case.get('group')!r}")
    # E(fee-rule-v2 isolation)
    rel = case.get("relative", "")
    if "references/" in rel or "fee-rule-v2" in rel:
        problems.append(f"{cid}: fee-rule-v2 leakage in path {rel!r}")
    if not rel.startswith("funds_word/"):
        warnings.append(f"{cid}: unexpected relative root {rel!r}")

    # C: source integrity
    src = SOURCE_ROOT / case.get("file", "")
    if not src.exists():
        problems.append(f"{cid}: source DOCX missing {src}")
        return
    actual_sha = sha256_file(src)
    if actual_sha != case.get("sha256"):
        problems.append(f"{cid}: source sha drift")

    paras = docx_paragraphs(src)
    full_text = docx_full_text(src)
    full_nopunct = strip_punct(full_text)
    stats["paragraphs"] += len(paras)

    # E: protection coherence
    prot_actual = docx_protection(src)
    prot_label = (case.get("document") or {}).get("protection", {}).get("protected")
    if prot_actual != prot_label:
        problems.append(f"{cid}: protection mismatch label={prot_label} actual={prot_actual}")

    n_para = (case.get("document") or {}).get("paragraph_count")
    if n_para is not None and n_para != len(paras):
        problems.append(f"{cid}: paragraph_count {n_para} != actual {len(paras)}")

    # A/D: rule_coverage
    for i, rc in enumerate(case.get("rule_coverage", [])):
        for k in RC_REQUIRED:
            if k not in rc:
                problems.append(f"{cid}: rule_coverage[{i}] missing {k}")
        if rc.get("status") not in STATUSES:
            problems.append(f"{cid}: rule_coverage[{i}] bad status {rc.get('status')!r}")
        if rc.get("scope") not in ("main", "summary"):
            problems.append(f"{cid}: rule_coverage[{i}] bad scope {rc.get('scope')!r}")
        q = rc.get("evidence_quote")
        if q:
            for f in fragments(q):
                cls = fragment_class(f, full_text, full_nopunct)
                if cls == "missing":
                    problems.append(
                        f"{cid}: rule_coverage[{i}] evidence_quote CONTENT not in source ({rc.get('rule_id')}/{rc.get('status')}): {f[:40]!r}"
                    )
                    stats.setdefault("evidence_defects", []).append(
                        {"case": cid, "idx": i, "rule": rc.get("rule_id"), "status": rc.get("status"), "fragment": f[:80]}
                    )
                elif cls == "punct":
                    warnings.append(
                        f"{cid}: rule_coverage[{i}] evidence_quote punct-only diff ({rc.get('rule_id')})"
                    )
        pi = rc.get("paragraph_index")
        if pi is not None and not (0 <= pi < len(paras)):
            problems.append(f"{cid}: rule_coverage[{i}] paragraph_index out of range")
        stats["coverage"] += 1

    # A/D: targets
    seen_ids = set()
    for i, t in enumerate(case.get("targets", [])):
        for k in TARGET_REQUIRED:
            if k not in t:
                problems.append(f"{cid}: targets[{i}] missing {k}")
        tid = t.get("target_id")
        if tid in seen_ids:
            problems.append(f"{cid}: duplicate target_id {tid}")
        seen_ids.add(tid)
        if t.get("op") not in OPS:
            problems.append(f"{cid}: targets[{i}] bad op {t.get('op')!r}")
        if prot_actual:
            problems.append(f"{cid}: target on protected document")
        stats["rule_targets"][t.get("rule_id")] = stats["rule_targets"].get(t.get("rule_id"), 0) + 1
        if t.get("op") != "append":
            ot = t.get("old_text")
            if not ot:
                problems.append(f"{cid}: targets[{i}] {t.get('op')} without old_text")
        # 冻结哈希自证：old_text_sha256=sha256(去空白old_text)；
        # paragraph_text_sha256=sha256(段落raw text) → 位置真实性硬校验
        exp_ots = hashlib.sha256(norm(t.get("old_text") or "").encode()).hexdigest()
        if t.get("old_text_sha256") and t["old_text_sha256"] != exp_ots:
            problems.append(f"{cid}: targets[{i}] old_text_sha256 mismatch")
        pi0 = t.get("paragraph_index")
        pts = t.get("paragraph_text_sha256")
        if isinstance(pi0, int) and 0 <= pi0 < len(paras) and pts:
            if hashlib.sha256(paras[pi0].encode()).hexdigest() != pts:
                problems.append(f"{cid}: targets[{i}] paragraph_text_sha256 mismatch (position forgery?)")
        for qk in ("old_text", "source_quote", "anchor_quote"):
            q = t.get(qk)
            if not q:
                continue
            for f in fragments(q):
                cls = fragment_class(f, full_text, full_nopunct)
                if cls == "missing":
                    problems.append(
                        f"{cid}: targets[{i}] {qk} CONTENT not in source: {f[:40]!r}"
                    )
                elif cls == "punct":
                    warnings.append(f"{cid}: targets[{i}] {qk} punct-only diff")
        if t.get("op") in ("append", "replace") and not t.get("required_text"):
            warnings.append(f"{cid}: targets[{i}] {t.get('op')} empty required_text")
        if t.get("op") == "delete" and t.get("required_text"):
            warnings.append(f"{cid}: targets[{i}] delete carries required_text")
        pi = t.get("paragraph_index")
        if pi is not None and not (0 <= pi < len(paras)):
            problems.append(f"{cid}: targets[{i}] paragraph_index out of range")
        stats["targets"] += 1

    # quality/review block
    lq = case.get("label_quality") or {}
    if lq.get("issue_count") != 0:
        problems.append(f"{cid}: label_quality.issue_count={lq.get('issue_count')}")
    if (case.get("review") or {}).get("status") != "completed":
        problems.append(f"{cid}: review not completed")
    if case.get("targets"):
        stats["with_targets"] += 1
    stats["uncertain"] += len(case.get("uncertain") or [])
    stats.setdefault("ineligible", [])
    if case.get("fund", {}).get("eligible") is False:
        stats["ineligible"].append(cid)
        if case.get("targets"):
            problems.append(f"{cid}: ineligible case carries targets")
    if "exclusion-money-market" in (case.get("stratum") or ""):
        stats["money_market"].append(cid)


def run(batch: int) -> dict:
    labels_sha = sha256_file(LABELS)
    selection_sha = sha256_file(SELECTION)
    labels = json.load(open(LABELS))
    selection = json.load(open(SELECTION))
    boundary = json.load(open(BOUNDARY))
    verification = json.load(open(VERIFICATION))

    env_problems: list[str] = []
    if labels_sha != EXPECTED_LABELS_SHA:
        env_problems.append(f"labels sha drift: {labels_sha}")
    if selection_sha != EXPECTED_SELECTION_SHA:
        env_problems.append(f"selection sha drift: {selection_sha}")
    if labels.get("schema") != EXPECTED_SCHEMA:
        env_problems.append(f"unexpected labels schema {labels.get('schema')!r}")
    lab = labels.get("labeler", {})
    for mk in ("primary_model", "review_model"):
        mv = str(lab.get(mk, ""))
        if "kimi" in mv.lower():
            env_problems.append(f"labeler.{mk} is engine family: {mv}")
        if "qwen" not in mv.lower():
            env_problems.append(f"labeler.{mk} unexpected: {mv}")
    if "second-batch-20261031" not in str(labels.get("batch_id", "")):
        env_problems.append(f"unexpected batch_id {labels.get('batch_id')!r}")

    sel_by_id = {c["case_id"]: c for c in selection["cases"]}
    cases = labels["cases"]
    if len(cases) != 100:
        env_problems.append(f"labels cases={len(cases)} != 100")
    if len(sel_by_id) != 100:
        env_problems.append(f"selection cases={len(sel_by_id)} != 100")
    id_sets_equal = set(sel_by_id) == {c["case_id"] for c in cases}
    if not id_sets_equal:
        env_problems.append("labels/selection case_id sets differ")
    dev = sum(1 for c in cases if c.get("group") == "dev")
    hold = sum(1 for c in cases if c.get("group") == "holdout")
    if (dev, hold) != (75, 25):
        env_problems.append(f"group split {dev}/{hold} != 75/25")

    ordered = sorted(cases, key=lambda c: (0 if c["group"] == "dev" else 1, c["case_id"]))
    if batch == 0:
        batch_cases = ordered
    else:
        batch_cases = ordered[(batch - 1) * 20 : batch * 20]

    problems: list[str] = []
    warnings: list[str] = []
    stats: dict = {"targets": 0, "coverage": 0, "with_targets": 0,
                   "uncertain": 0, "paragraphs": 0, "rule_targets": {}, "ineligible": [],
                   "money_market": []}
    for case in batch_cases:
        check_case(case, sel_by_id.get(case["case_id"], {}), problems, warnings, stats)

    report = {
        "script": "tools/evaluation/w3_reverify_second_batch_labels_20261101.py",
        "batch": "all" if batch == 0 else batch,
        "cases": [c["case_id"] for c in batch_cases],
        "labels_sha256": labels_sha,
        "selection_sha256": selection_sha,
        "envelope_problems": env_problems,
        "problems": problems,
        "warnings": warnings,
        "counts": {
            "cases": len(batch_cases),
            "targets": stats["targets"],
            "coverage_entries": stats["coverage"],
            "cases_with_targets": stats["with_targets"],
            "uncertain_entries": stats["uncertain"],
            "ineligible_cases": stats["ineligible"],
        },
    }

    if batch == 0:
        # G: total ledger recompute vs frozen verification report
        exp = verification.get("totals", {})
        for key, mine in (("targets", stats["targets"]),
                          ("coverage_entries", stats["coverage"]),
                          ("cases_with_targets", stats["with_targets"]),
                          ("uncertain", stats["uncertain"])):
            got = exp.get(key)
            if got != mine:
                report["problems"].append(f"ledger mismatch {key}: verification={got} recompute={mine}")
        vrt = verification.get("rule_target_totals", {})
        if {k: v for k, v in sorted(stats["rule_targets"].items())} != {k: v for k, v in sorted(vrt.items())}:
            report["problems"].append("rule_target_totals mismatch vs verification report")
        if verification.get("problems"):
            report["problems"].append("frozen verification carries problems")
        # E: boundary ledger（对照冻结 boundary 工件的五个清单，{count,detail,cases[]} 结构）
        def bcases(key: str) -> list:
            blk = boundary.get(key) or {}
            cs = blk.get("cases") or []
            return [x["case_id"] if isinstance(x, dict) else str(x) for x in cs]

        b_unpar_ids = bcases("unparseable")
        b_prot_ids = bcases("protected")
        b_excl_ids = bcases("excluded_from_modification_denominator")
        excl_ids = sorted(bcases("explicit_exclusion_type_kept_in_denominator"))
        zero_ids = sorted(bcases("zero_target_cases_kept_in_denominator"))
        mm = sorted(stats["money_market"])
        report["boundary"] = {
            "unparseable": b_unpar_ids,
            "protected": b_prot_ids,
            "excluded_from_denominator": b_excl_ids,
            "explicit_exclusion_kept": excl_ids,
            "zero_target_kept_n": len(zero_ids),
            "money_market_stratum": mm,
            "ineligible_cases": sorted(stats["ineligible"]),
        }
        if b_unpar_ids or b_prot_ids or b_excl_ids:
            report["problems"].append("boundary lists not empty as declared")
        if mm != excl_ids:
            report["problems"].append(f"money-market stratum {mm} != boundary explicit_exclusion {excl_ids}")
        # zero_target 边界清单必须与 labels 实测一致
        actual_zero = sorted(c["case_id"] for c in cases if not c.get("targets"))
        report["boundary"]["actual_zero_target_n"] = len(actual_zero)
        if actual_zero != zero_ids:
            report["problems"].append(
                f"zero-target mismatch: boundary={len(zero_ids)} labels-recompute={len(actual_zero)}"
            )
        # review completed 100
        done = sum(1 for c in cases if (c.get("review") or {}).get("status") == "completed")
        if done != 100:
            report["problems"].append(f"review completed {done}/100")

    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True, help="1..5 or 'all'")
    args = ap.parse_args()
    batch = 0 if args.batch == "all" else int(args.batch)
    report = run(batch)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    name = "summary.json" if batch == 0 else f"batch-{batch}.json"
    out = OUTDIR / name
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    n_prob = len(report["problems"]) + len(report["envelope_problems"])
    print(f"{out}: cases={report['counts']['cases']} targets={report['counts']['targets']} "
          f"problems={n_prob} warnings={len(report['warnings'])}")
    if n_prob:
        print("PROBLEMS:", file=sys.stderr)
        for p in report["envelope_problems"] + report["problems"]:
            print(" -", p, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
