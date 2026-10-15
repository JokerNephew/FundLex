"""Freeze the P6 real-revision evaluation sample (20 dev + 8 holdout) from funds_word.

Selection is deterministic and stratified on the coverage axes the guide actually
branches on (share-class count, service fee, floating fee) plus structure and length
proxies, so the 28 contracts are not "the easiest ones". Every chosen file's SHA-256
must be present in the frozen data manifest; the manifest of the run records the
source path, hash, size, paragraph count and the stratum reason for each case.

The holdout group is written but NOT read while developing; only the dev group feeds
the optimisation loop. Run:

    .venv/bin/python -X utf8 -m tools.evaluation.p6_select --output var/recall-first-evaluation/p6
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

# Name-derived proxies. They never decide edit behaviour; they only spread the sample
# across the structures the guide conditions on.
QDII = re.compile(r"QDII|纳斯达克|恒生|港股通|香港|美国|全球|海外|标普|境外|日经|德国|法国|亚太")
FOF = re.compile(r"FOF|基金中基金")
HOLD = re.compile(r"定期开放|持有期|封闭")
SPONSOR = re.compile(r"发起式")
ACTIVE = re.compile(r"混合型|股票型|债券型|灵活配置")
EXCLUDED = re.compile(r"交易型开放式指数|ETF|货币市场|同业存单")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def paragraphs_of(path: Path) -> list[str]:
    with ZipFile(path) as package:
        root = etree.fromstring(package.read("word/document.xml"),
                                parser=etree.XMLParser(resolve_entities=False, no_network=True))
    body = root.find(Q("body"))
    return ["".join(node.text or "" for node in paragraph.iter(Q("t")))
            for paragraph in body.iter(Q("p"))]


def stratum(name: str, paragraphs: list[str], size: int) -> str:
    flags = []
    if QDII.search(name):
        flags.append("qdii")
    if FOF.search(name):
        flags.append("fof")
    if HOLD.search(name):
        flags.append("hold")
    if SPONSOR.search(name):
        flags.append("sponsor")
    if EXCLUDED.search(name):
        flags.append("likely_excluded")
    elif ACTIVE.search(name):
        flags.append("active")
    flags.append("long" if len(paragraphs) >= 260 else "short" if len(paragraphs) <= 150 else "mid")
    flags.append("big" if size >= 170_000 else "small")
    return "+".join(flags)


def load_manifest(root: Path) -> dict[str, tuple[str, int]]:
    """relative path -> (sha256, bytes) from the frozen data manifest."""
    table: dict[str, tuple[str, int]] = {}
    for line in (root / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        digest, relative, size = line.split()
        table[relative] = (digest, int(size))
    return table


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default="/home/opencode/data")
    parser.add_argument("--output", default="var/recall-first-evaluation/p6")
    parser.add_argument("--dev", type=int, default=20)
    parser.add_argument("--holdout", type=int, default=8)
    args = parser.parse_args()

    data_root = Path(args.data_root)
    words = data_root / "funds_word"
    manifest = load_manifest(data_root)
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    for path in sorted(words.glob("*.docx")):
        relative = f"funds_word/{path.name}"
        entry = manifest.get(relative)
        if entry is None:
            continue
        digest, size = entry
        if sha256_file(path) != digest:
            raise SystemExit(f"manifest mismatch: {relative}")
        paragraphs = paragraphs_of(path)
        rows.append({
            "file": path.name, "relative": relative, "sha256": digest, "bytes": size,
            "paragraphs": len(paragraphs),
            "chars": sum(len(item) for item in paragraphs),
            "stratum": stratum(path.name, paragraphs, size),
        })

    # Stratified pick: group by the primary structural flag, then take a deterministic
    # stride within each group so a large stratum still contributes a spread of dates and
    # sizes rather than the first N files.
    def primary(row: dict) -> str:
        for flag in ("likely_excluded", "qdii", "fof", "active"):
            if flag in row["stratum"].split("+"):
                return flag
        return "other"

    buckets: dict[str, list[dict]] = {}
    for row in rows:
        buckets.setdefault(primary(row), []).append(row)

    order = ["active", "qdii", "fof", "likely_excluded", "other"]
    total = args.dev + args.holdout
    # Target share per stratum, capped by how many contracts it holds. 20/28 must be
    # eligible-and-likely-editable; QDII/FOF give the fee/currency variety, and a small
    # likely-excluded slice proves the qualification channel still reports exclusions.
    want = {"active": 16, "qdii": 3, "fof": 4, "likely_excluded": 3, "other": 2}
    picked: list[dict] = []
    for name in order:
        bucket = buckets.get(name) or []
        take = min(want.get(name, 0), len(bucket))
        if take:
            stride = max(1, len(bucket) // take)
            picked.extend(bucket[(index * stride) % len(bucket)] for index in range(take))
    # Fill any shortfall from the remaining largest strata, still with a stride.
    if len(picked) < total:
        seen = {row["sha256"] for row in picked}
        pool = [row for row in rows if row["sha256"] not in seen]
        need = total - len(picked)
        stride = max(1, len(pool) // need)
        picked.extend(pool[(index * stride) % len(pool)] for index in range(need))
    picked = picked[:total]
    # Interleave dev/holdout so neither group is all-QDII (no case is read for holdout
    # tuning; the split only needs to be the same distribution).
    dev: list[dict] = []
    holdout: list[dict] = []
    for index, row in enumerate(picked):
        (holdout if index % 7 == 3 else dev).append(row)
    while len(holdout) > args.holdout:
        dev.append(holdout.pop())
    while len(dev) > args.dev:
        holdout.append(dev.pop(0))

    for group, items in (("dev", dev), ("holdout", holdout)):
        for number, row in enumerate(sorted(items, key=lambda item: item["file"]), start=1):
            row["case_id"] = f"D{number:02d}" if group == "dev" else f"H{number:02d}"
            row["group"] = group
        items.sort(key=lambda item: item["case_id"])

    cases = dev + holdout
    selection = {
        "schema": "fundlex-p6-selection-v1",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "samples_root": str(words),
        "manifest": str(data_root / "MANIFEST.sha256"),
        "guide": "guides/builtin_guide_v1.json",
        "engine": "recall_first",
        "counts": {"dev": len(dev), "holdout": len(holdout), "total": len(cases)},
        "strata": {name: len(buckets.get(name) or []) for name in order},
        "cases": cases,
    }
    (output / "selection.json").write_text(json.dumps(selection, ensure_ascii=False, indent=1) + "\n",
                                           encoding="utf-8")
    print(json.dumps({"dev": [row["case_id"] for row in dev],
                      "holdout": [row["case_id"] for row in holdout],
                      "strata": selection["strata"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
