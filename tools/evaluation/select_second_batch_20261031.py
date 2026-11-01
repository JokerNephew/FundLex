#!/usr/bin/env python3
"""Stratified, frozen selection for the second evaluation wave (~100 contracts).

Reads the top-level ``funds_word/*.docx`` corpus, removes every sha256 that is
part of the frozen first batch (2026-10-28), groups near-duplicates of the same
fund, and picks ~100 contracts covering the wave-2 strata:

short / long, A/C, multi-class with uncommon letters (A/C/E/Y...), QDII, FOF,
index / ETF-feeder, bond / hybrid, maybe-satisfied, body+summary,
cross-paragraph / table structures, and explicit exclusion types.

The selection is independent of any engine output: it reads only the original
DOCX files, the first-batch *selection manifest* (hash exclusion only), and
heuristics.  It never reads var/recall-first-evaluation results.

Usage:
    .venv/bin/python tools/evaluation/select_second_batch_20261031.py \
        [--out docs/evidence/selection-second-batch-20261031.json] \
        [--features-out var/recall-first-evaluation/second-batch-20261031/corpus-features.json]
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import random
import re
import sys
import zipfile
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOT = Path("/home/opencode/fundlex/funds_word")
FIRST_BATCH_SELECTION = ROOT / "docs/evidence/selection-first-batch-20261028.json"
DEFAULT_GUIDE = ROOT / "references/source/v4存量基金适用销售费用新规的基金合同修改指引_文案勘误版.docx"
DEFAULT_OUT = ROOT / "docs/evidence/selection-second-batch-20261031.json"
DEFAULT_FEATURES = ROOT / "var/recall-first-evaluation/second-batch-20261031/corpus-features-second-batch-20261031.json"
SEED = 20261031
TARGET_TOTAL = 100
HOLDOUT_FRACTION = 0.25


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


SUMMARY_RE = re.compile(r"基金合同内容摘要|招募说明书摘要")
FEE_WORDS = ("申购费", "赎回费", "销售服务费")
FLOAT_WORDS = ("超额管理费", "或有管理费", "浮动管理费", "业绩报酬")
CLASS_RE = re.compile(r"([A-ZＡ-Ｚ])类(?:基金份额|份额|收费|的申|\(|（|,|，|、|\s|$)")
OLD_ARRANGEMENT_RE = re.compile(r"(划付指令|自动支付|一次性支付|无需.{0,8}划款指令|发送.{0,8}指令)")
NEW_MECHANISM_RE = re.compile(r"返还给投资者")


def _norm_letter(ch: str) -> str:
    if "Ａ" <= ch <= "Ｚ":
        return chr(ord(ch) - 0xFEE0)
    return ch


def normalize_fund_base(name: str) -> str:
    base = name.rsplit(".", 1)[0]
    base = re.sub(r"(?:_?\d{8})+$", "", base)
    base = re.sub(r"[（(][^)）]*(?:QDII|FOF|LOF|ETF)[^)）]*[)）]", "", base)
    for token in ("广发", "基金合同", "修订原件备份", "拒绝修订", "修订", "发起式"):
        base = base.replace(token, "")
    return re.sub(r"[\s_\-—–、·]+", "", base)


def extract_features(path: Path) -> dict[str, Any] | None:
    try:
        import docx  # imported inside the worker for ProcessPool pickling

        document = docx.Document(str(path))
        paragraphs = [p.text or "" for p in document.paragraphs]
        nonempty = [(i, t) for i, t in enumerate(paragraphs) if t.strip()]
        all_text = "\n".join(paragraphs)
        compact = re.sub(r"\s+", "", all_text)
        summary_start = None
        for idx, text in enumerate(paragraphs):
            t = text.strip()
            if not t or len(t) > 60 or "摘要" not in t:
                continue
            style = ""
            try:
                style = (document.paragraphs[idx].style.name or "").lower()
            except Exception:
                pass
            if style.startswith("toc"):
                continue
            if style.startswith("heading") or re.match(r"^(?:第[一二三四五六七八九十百]+部分|[一二三四五六七八九十百]+、)", t):
                summary_start = idx
                break
        summary_paras = 0 if summary_start is None else len([1 for i, _ in nonempty if i >= summary_start])
        tables = document.tables
        fee_tables = 0
        for table in tables:
            try:
                cell_text = "".join(c.text for row in table.rows for c in row.cells)
            except Exception:
                continue
            if any(w in cell_text for w in FEE_WORDS) or "管理费率" in cell_text:
                fee_tables += 1
        letter_counts: dict[str, int] = {}
        for m in CLASS_RE.finditer(compact):
            letter = _norm_letter(m.group(1))
            if letter in {"A", "B", "C", "D", "E", "F", "H", "I", "R", "Y"}:
                letter_counts[letter] = letter_counts.get(letter, 0) + 1
        class_letters = sorted(k for k, v in letter_counts.items() if v >= 2)
        try:
            with zipfile.ZipFile(path) as archive:
                settings = archive.read("word/settings.xml")
                protected = b"<w:documentProtection" in settings
                xml = archive.read("word/document.xml")
        except Exception:
            protected, xml = False, b""
        bookmarks = xml.count(b"<w:bookmarkStart")
        hyperlinks = xml.count(b"<w:hyperlink")
        fee_para_split = 0
        for _i, t in nonempty:
            if not any(w in t for w in FEE_WORDS):
                continue
            stripped = t.strip()
            if stripped and stripped[-1] not in "。；：；）).:;":
                fee_para_split += 1
        name = path.name
        upper_name = name.upper()
        fund_type_hint = None
        for key, hint in (
            ("货币市场", "money_market"),
            ("债券", "bond"),
            ("混合", "hybrid"),
            ("股票", "equity"),
            ("指数", "index"),
            ("联接", "etf_feeder"),
            ("ETF", "etf"),
            ("基金中基金", "fof"),
            ("FOF", "fof"),
            ("QDII", "qdii"),
            ("LOF", "lof"),
            ("货币", "money_market"),
        ):
            if key in name or key in upper_name:
                fund_type_hint = hint
                break
        if fund_type_hint is None:
            m = re.search(r"(债券型|混合型|股票型|指数型|货币市场基金|FOF|QDII)", compact[:4000])
            if m:
                token = m.group(1)
                fund_type_hint = {
                    "债券型": "bond", "混合型": "hybrid", "股票型": "equity",
                    "指数型": "index", "货币市场基金": "money_market",
                    "FOF": "fof", "QDII": "qdii",
                }.get(token)
        qdii = "QDII" in upper_name or "合格境内机构投资者" in compact[:6000]
        fof = fund_type_hint == "fof" or "基金中基金" in name
        etf_feeder = "联接" in name
        index = "指数" in name or (qdii and "指数" in compact[:4000])
        old_arrangement = any(
            "销售服务费" in t and bool(OLD_ARRANGEMENT_RE.search(t)) for _i, t in nonempty
        )
        has_new_mechanism = any(
            "销售服务费" in t and bool(NEW_MECHANISM_RE.search(t)) for _i, t in nonempty
        )
        maybe_satisfied = has_new_mechanism and not old_arrangement
        partially_updated = has_new_mechanism and old_arrangement
        currency_usd = compact.count("美元")
        currency_variants = currency_usd >= 2 and "A类" in compact
        floating = any(w in compact for w in FLOAT_WORDS)
        return {
            "file": name,
            "sha256": _sha256(path.read_bytes()),
            "bytes": path.stat().st_size,
            "paragraph_count": len(paragraphs),
            "summary_start": summary_start,
            "summary_paragraphs": summary_paras,
            "has_summary": summary_start is not None,
            "protected": bool(protected),
            "table_count": len(tables),
            "fee_tables": fee_tables,
            "class_letters": class_letters,
            "multi_class": len(class_letters) >= 2,
            "single_class": len(class_letters) == 0,
            "uncommon_letters": sorted(set(class_letters) - {"A", "C"}),
            "currency_variants": bool(currency_variants),
            "qdii": bool(qdii),
            "fof": bool(fof),
            "etf_feeder": bool(etf_feeder),
            "index": bool(index),
            "fund_type_hint": fund_type_hint,
            "floating_fee": bool(floating),
            "maybe_satisfied": bool(maybe_satisfied),
            "partially_updated": bool(partially_updated),
            "new_mechanism_present": bool(has_new_mechanism),
            "old_payment_arrangement": bool(old_arrangement),
            "bookmarks": int(bookmarks),
            "hyperlinks": int(hyperlinks),
            "fee_para_split": int(fee_para_split),
            "text_sha256_compact": _sha256(re.sub(r"\d", "#", compact).encode("utf-8")),
            "fund_base": normalize_fund_base(name),
        }
    except Exception as exc:
        return {"file": path.name, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}


def strata_of(f: dict[str, Any]) -> list[str]:
    s: list[str] = []
    if f["protected"]:
        s.append("protected-boundary")
    if f.get("fund_type_hint") == "money_market":
        s.append("exclusion-money-market")
    if not f["has_summary"]:
        s.append("no-summary")
    else:
        s.append("body+summary")
    if f["bytes"] < 135_000:
        s.append("short")
    if f["bytes"] > 165_000:
        s.append("long")
    if f["qdii"]:
        s.append("QDII")
    if f["fof"]:
        s.append("FOF")
    if f["etf_feeder"]:
        s.append("etf-feeder")
    if f["index"]:
        s.append("index")
    if f.get("fund_type_hint") == "bond":
        s.append("bond")
    if f.get("fund_type_hint") == "hybrid":
        s.append("hybrid")
    if f.get("fund_type_hint") == "equity":
        s.append("equity")
    if f["multi_class"]:
        if f["uncommon_letters"]:
            s.append("multi-class-uncommon(A/C/E/Y)")
        else:
            s.append("multi-class-A/C")
    if f["single_class"]:
        s.append("single-class")
    if f["currency_variants"]:
        s.append("currency-variants")
    if f["floating_fee"]:
        s.append("floating-fee")
    if f["maybe_satisfied"]:
        s.append("maybe-satisfied")
    if f.get("partially_updated"):
        s.append("partially-updated")
    if f["old_payment_arrangement"] and not f["maybe_satisfied"]:
        s.append("old-arrangement-needs-change")
    if f["fee_tables"] >= 1:
        s.append("fee-tables")
    if f["fee_para_split"] >= 6:
        s.append("cross-paragraph-split")
    return s


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-root", default=str(CORPUS_ROOT))
    parser.add_argument("--first-batch-selection", default=str(FIRST_BATCH_SELECTION))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--features-out", default=str(DEFAULT_FEATURES))
    parser.add_argument("--target-total", type=int, default=TARGET_TOTAL)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    corpus_root = Path(args.corpus_root)
    files = sorted(corpus_root.glob("*.docx"))
    non_docx = [p.name for p in corpus_root.iterdir() if p.is_file() and p.suffix.lower() != ".docx"]
    print(f"[select] corpus root files: {len(files)} docx; non-docx files: {len(non_docx)}")

    first = json.loads(Path(args.first_batch_selection).read_text(encoding="utf-8"))
    first_hashes = {c["sha256"] for c in first["cases"]}
    first_bases: dict[str, str] = {}
    for c in first["cases"]:
        first_bases.setdefault(normalize_fund_base(c["file"]), c["group"])
        first_bases.setdefault(normalize_fund_base(c["file"]), c["case_id"])
    first_base_map = {normalize_fund_base(c["file"]): c["case_id"] for c in first["cases"]}
    first_group_map = {normalize_fund_base(c["file"]): c["group"] for c in first["cases"]}

    features: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for idx, item in enumerate(pool.map(extract_features, files, chunksize=8), 1):
            features.append(item)
            if idx % 50 == 0:
                print(f"[select] feature extraction {idx}/{len(files)}", flush=True)
    errors = [f for f in features if f.get("error")]
    ok = [f for f in features if not f.get("error")]
    print(f"[select] parsed {len(ok)} ok, {len(errors)} errors")
    for e in errors:
        print(f"  error: {e['file']}: {e['error']}")

    overlap = [f for f in ok if f["sha256"] in first_hashes]
    for f in overlap:
        print(f"[select] hash overlap with first batch (excluded): {f['file']}")
    candidates = [f for f in ok if f["sha256"] not in first_hashes]

    by_base: dict[str, list[dict[str, Any]]] = {}
    for f in candidates:
        by_base.setdefault(f["fund_base"], []).append(f)

    rng = random.Random(SEED)
    quotas: list[tuple[str, int]] = [
        ("protected-boundary", 3),
        ("exclusion-money-market", 3),
        ("no-summary", 2),
        ("maybe-satisfied", 5),
        ("multi-class-uncommon(A/C/E/Y)", 8),
        ("currency-variants", 3),
        ("floating-fee", 3),
        ("QDII", 7),
        ("FOF", 6),
        ("etf-feeder", 5),
        ("index", 8),
        ("single-class", 6),
        ("fee-tables", 8),
        ("partially-updated", 4),
        ("cross-paragraph-split", 6),
        ("old-arrangement-needs-change", 8),
        ("short", 10),
        ("long", 14),
        ("bond", 10),
        ("hybrid", 10),
        ("equity", 5),
    ]

    protect_from_trim = ("exclusion-money-market", "no-summary", "protected-boundary", "maybe-satisfied")
    trim_minimums = {
        "QDII": 5, "FOF": 5, "etf-feeder": 4, "index": 6,
        "multi-class-uncommon(A/C/E/Y)": 6, "currency-variants": 2,
        "single-class": 4, "floating-fee": 2, "maybe-satisfied": 3,
        "partially-updated": 3,
        "fee-tables": 6, "cross-paragraph-split": 5,
        "old-arrangement-needs-change": 5, "short": 10, "long": 12,
        "bond": 8, "hybrid": 8, "equity": 3,
    }

    chosen_bases: set[str] = set()
    chosen: list[dict[str, Any]] = []
    strata_hit: dict[str, list[str]] = {}

    def base_of(f: dict[str, Any]) -> str:
        return f["fund_base"]

    def pick(f: dict[str, Any], why: str) -> None:
        f["stratum_matched"] = strata_of(f)
        f["choose_reason"] = why
        chosen.append(f)
        chosen_bases.add(base_of(f))
        for s in f["stratum_matched"]:
            strata_hit.setdefault(s, []).append(f["file"])

    def stratum_pool(name: str) -> list[dict[str, Any]]:
        pool = [f for f in candidates if name in strata_of(f) and base_of(f) not in chosen_bases]
        rng.shuffle(pool)
        return pool

    for name, want in quotas:
        pool = stratum_pool(name)
        already = {c["file"] for c in chosen}
        count = 0
        for f in pool:
            if count >= want:
                break
            if f["file"] in already:
                continue
            pick(f, f"quota:{name}")
            count += 1
        print(f"[select] quota {name}: wanted {want}, picked {count}")

    # trim to the target size, protecting scarce strata and exclusion samples
    if len(chosen) > args.target_total:
        counts = {}
        for c in chosen:
            for s_ in c["stratum_matched"]:
                counts[s_] = counts.get(s_, 0) + 1
        removable = [
            c for c in chosen
            if not any(k in c["stratum_matched"] for k in protect_from_trim)
            and "商业不动产" not in c["file"]
        ]
        rng.shuffle(removable)
        removed = 0
        for c in removable:
            if len(chosen) - removed <= args.target_total:
                break
            ok_drop = all(
                counts.get(s_, 0) - 1 >= trim_minimums.get(s_, 0)
                for s_ in c["stratum_matched"]
            )
            if not ok_drop:
                continue
            for s_ in c["stratum_matched"]:
                counts[s_] -= 1
            c["trimmed"] = True
            removed += 1
        if removed:
            chosen = [c for c in chosen if not c.get("trimmed")]
        # rebuild bookkeeping after trim
        strata_hit = {}
        for c in chosen:
            for s_ in c["stratum_matched"]:
                strata_hit.setdefault(s_, []).append(c["file"])
        print(f"[select] trimmed {removed} cases to hit target {args.target_total}")

    remain = [
        f for f in candidates
        if base_of(f) not in chosen_bases
        and "exclusion-money-market" not in strata_of(f)
        and "商业不动产" not in f["file"]
    ]
    rng.shuffle(remain)
    chosen_files = {c["file"] for c in chosen}
    for f in remain:
        if len(chosen) >= args.target_total:
            break
        if f["file"] in chosen_files:
            continue
        pick(f, "random-fill")

    # near-duplicate grouping: keep the whole fund group on one side
    rng2 = random.Random(SEED + 1)
    holdout_bases = set()
    dev_bases = set()
    def sorted_bases(items: list[dict[str, Any]]) -> list[str]:
        gs = sorted({base_of(f) for f in items})
        rng2.shuffle(gs)
        return gs
    # seed sides with first-batch near duplicates
    for f in chosen:
        case = first_base_map.get(f["fund_base"])
        grp = first_group_map.get(f["fund_base"])
        if case and grp == "holdout":
            holdout_bases.add(base_of(f))
        elif case and grp == "dev":
            dev_bases.add(base_of(f))
    n_holdout_target = round(len(chosen) * HOLDOUT_FRACTION)
    rest = sorted_bases([f for f in chosen if base_of(f) not in holdout_bases and base_of(f) not in dev_bases])
    in_holdout = [f for f in chosen if base_of(f) in holdout_bases]
    for b in rest:
        if len(in_holdout) >= n_holdout_target:
            break
        holdout_bases.add(b)
        in_holdout = [f for f in chosen if base_of(f) in holdout_bases]

    cases: list[dict[str, Any]] = []
    dev_n = holdout_n = 0
    for f in sorted(chosen, key=lambda x: (base_of(x), x["file"])):
        group = "holdout" if base_of(f) in holdout_bases else "dev"
        if group == "dev":
            dev_n += 1
            case_id = f"W2D{dev_n:02d}"
        else:
            holdout_n += 1
            case_id = f"W2H{holdout_n:02d}"
        near = first_base_map.get(f["fund_base"])
        cases.append({
            "case_id": case_id,
            "group": group,
            "file": f["file"],
            "relative": f"funds_word/{f['file']}",
            "sha256": f["sha256"],
            "bytes": f["bytes"],
            "stratum": ";".join(f["stratum_matched"]) or "general",
            "rationale": f["choose_reason"],
            "fund_base": f["fund_base"],
            "near_duplicate_of_first_batch_case": near,
            "predicted_features": {
                "paragraph_count": f["paragraph_count"],
                "has_summary": f["has_summary"],
                "summary_paragraphs": f["summary_paragraphs"],
                "protected": f["protected"],
                "table_count": f["table_count"],
                "fee_tables": f["fee_tables"],
                "class_letters": f["class_letters"],
                "uncommon_letters": f["uncommon_letters"],
                "currency_variants": f["currency_variants"],
                "fund_type_hint": f["fund_type_hint"],
                "qdii": f["qdii"],
                "fof": f["fof"],
                "etf_feeder": f["etf_feeder"],
                "index": f["index"],
                "floating_fee": f["floating_fee"],
                "maybe_satisfied": f["maybe_satisfied"],
                "old_payment_arrangement": f["old_payment_arrangement"],
                "bookmarks": f["bookmarks"],
                "hyperlinks": f["hyperlinks"],
                "fee_para_split": f["fee_para_split"],
            },
        })

    manifest = {
        "schema": "fundlex-second-batch-selection-v1",
        "frozen_at": now_iso(),
        "seed": SEED,
        "source_root": str(corpus_root),
        "source_manifest": "funds_word (top level *.docx only)",
        "guide": str(DEFAULT_GUIDE.relative_to(ROOT)),
        "guide_sha256": _sha256(DEFAULT_GUIDE.read_bytes()),
        "counts": {"dev": dev_n, "holdout": holdout_n, "total": len(cases)},
        "corpus": {
            "root_docx": len(files),
            "parsed_ok": len(ok),
            "parse_errors": errors,
            "non_docx_files": non_docx,
            "first_batch_hash_overlaps_removed": [f["file"] for f in overlap],
            "first_batch_case_count": len(first_hashes),
        },
        "strata_coverage": {k: len(v) for k, v in sorted(strata_hit.items())},
        "excluded_from_modification_denominator": [],
        "notes": [
            "Selection is independent of engine output: only original DOCX files, heuristics and the first-batch selection hashes were read; no var/recall-first-evaluation results were read.",
            "Near-duplicate fund groups (normalized fund base name) are kept on one side; near-duplicates of first-batch cases inherit the first-batch side to avoid dev/holdout leakage.",
            "Strata labels are pre-label heuristics from the original contract text; authoritative facts come from the independent labels.",
            "maybe-satisfied is a heuristic (new G16-style mechanism present, old arrangement absent); final satisfied/not-applicable status is decided by the blind labels.",
            "Money-market funds are selected as the explicit exclusion-type stratum (not a sale-fee guide target population); labels decide eligibility with evidence.",
            "No cherry-picking by success: strata quotas plus seeded random fill over the whole root corpus.",
        ],
        "cases": cases,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    features_path = Path(args.features_out)
    features_path.parent.mkdir(parents=True, exist_ok=True)
    features_path.write_text(json.dumps({
        "generated_at": manifest["frozen_at"],
        "tool": os.path.relpath(Path(__file__).resolve(), ROOT),
        "corpus_root": str(corpus_root),
        "files": features,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[select] wrote {out_path} sha256={_sha256(out_path.read_bytes())}")
    print(f"[select] wrote {features_path}")
    print(f"[select] dev={dev_n} holdout={holdout_n} total={len(cases)}")
    print("[select] strata coverage:")
    for k, v in sorted(strata_hit.items()):
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
