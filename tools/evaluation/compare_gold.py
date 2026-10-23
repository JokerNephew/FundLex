"""Freeze independent textual gold for the compare corpus.

The gold extractor reads OOXML itself (without importing the compare parser),
keeps paragraph/table boundaries and records SequenceMatcher offsets.  It is
only a scoring oracle; it never decides whether a production result is valid.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
import re
from difflib import SequenceMatcher
from pathlib import Path

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
Q = lambda name: f"{{{W}}}{name}"


def blocks(path: str | Path) -> list[dict]:
    with zipfile.ZipFile(path) as package:
        root = etree.fromstring(package.read("word/document.xml"), etree.XMLParser(resolve_entities=False, no_network=True))
    body = root.find(Q("body")); result = []
    if body is None: return result
    table = 0; paragraph = 0
    for child in body:
        if child.tag == Q("p"):
            result.append({"ordinal": len(result), "location": f"p{paragraph}", "text": text(child), "kind": "paragraph"}); paragraph += 1
        elif child.tag == Q("tbl"):
            for ri, row in enumerate(child.findall(Q("tr"))):
                for ci, cell in enumerate(row.findall(Q("tc"))):
                    for pi, p in enumerate(cell.findall(Q("p"))):
                        result.append({"ordinal": len(result), "location": f"tbl{table}/r{ri}/c{ci}/p{pi}", "text": text(p), "kind": "table_paragraph"})
            table += 1
        elif child.tag == Q("sdt"):
            for pi, p in enumerate(child.iter(Q("p"))):
                result.append({"ordinal": len(result), "location": f"sdt{len(result)}/p{pi}", "text": text(p), "kind": "paragraph"})
    return result


def text(node: etree._Element) -> str:
    out = []
    for item in node.iter():
        if item.tag in {Q("t"), Q("delText")}: out.append(item.text or "")
        elif item.tag in {Q("br"), Q("cr")}: out.append("\n")
        elif item.tag == Q("tab"): out.append("\t")
    return "".join(out)


def flatten(items: list[dict]) -> tuple[str, list[tuple[int, int, int]]]:
    value, ranges = [], []
    for index, item in enumerate(items):
        start = len(value); value.extend(item["text"]); end = len(value)
        ranges.append((start, end, index))
        if index + 1 < len(items): value.append("\n")
    return "".join(value), ranges


def _locate(offset: int, ranges: list[tuple[int, int, int]]) -> tuple[int | None, int]:
    for start, end, index in ranges:
        if start <= offset <= end: return index, max(0, offset - start)
    return (ranges[-1][2], max(0, ranges[-1][1] - ranges[-1][0])) if ranges else (None, 0)


def gold_pair(base: str | Path, mutated: str | Path, *, expected_zero: bool = False) -> dict:
    left, right = blocks(base), blocks(mutated)
    left_text, left_ranges = flatten(left); right_text, right_ranges = flatten(right)
    ops = []
    windows = []
    # Exact paragraph anchors keep this independent oracle bounded on long
    # repetitive contracts. Only unmatched windows need character scoring.
    for tag, ai, az, bi, bz in SequenceMatcher(None, [b['text'] for b in left], [b['text'] for b in right], autojunk=False).get_opcodes():
        if tag == 'equal': continue
        a0 = left_ranges[ai][0] if ai < len(left_ranges) else len(left_text)
        a1 = left_ranges[az - 1][1] if az > ai else a0
        b0 = right_ranges[bi][0] if bi < len(right_ranges) else len(right_text)
        b1 = right_ranges[bz - 1][1] if bz > bi else b0
        windows.append((a0, a1, b0, b1))
    raw_ops = []
    for a0, a1, b0, b1 in windows:
        for tag, ai, az, bi, bz in SequenceMatcher(None, left_text[a0:a1], right_text[b0:b1], autojunk=False).get_opcodes():
            raw_ops.append((tag, a0 + ai, a0 + az, b0 + bi, b0 + bz))
    for tag, i1, i2, j1, j2 in raw_ops:
        if tag == "equal": continue
        # Paragraph separator changes are structural noise; only actual visible
        # characters count toward textual recall.
        before = left_text[i1:i2]; after = right_text[j1:j2]
        if before.replace("\n", "").replace("\t", "").strip() == after.replace("\n", "").replace("\t", "").strip():
            continue
        li, lo = _locate(i1, left_ranges); ri, ro = _locate(j1, right_ranges)
        ops.append({"tag": tag, "left": {"ordinal": li, "location": left[li]['location'] if li is not None else '', "offset": lo, "text": before[:512], "length": len(before), "start": i1, "end": i2,
                                           "sha256": hashlib.sha256(before.encode()).hexdigest()},
                    "right": {"ordinal": ri, "location": right[ri]['location'] if ri is not None else '', "offset": ro, "text": after[:512], "length": len(after), "start": j1, "end": j2,
                                            "sha256": hashlib.sha256(after.encode()).hexdigest()}})
    compact_left = [{"ordinal": b["ordinal"], "location": b["location"], "length": len(b["text"])} for b in left]
    compact_right = [{"ordinal": b["ordinal"], "location": b["location"], "length": len(b["text"])} for b in right]
    # A structural mutation is a zero-diff fixture only when the visible
    # character stream is actually unchanged.  This catches malformed merge
    # fixtures that accidentally move a heading while joining paragraphs.
    # Paragraph breaks and all horizontal whitespace are structural noise for
    # this zero-diff classification; visible character order must still match.
    zero_stream = re.sub(r"\s+", "", left_text) == re.sub(r"\s+", "", right_text)
    # The visible OOXML stream is the independent decision.  The manifest
    # flag is retained only as an audit signal; it must never make a real
    # mutation into a zero case (or make a structural-only case non-zero).
    declared_expected_zero = bool(expected_zero)
    expected_zero = bool(zero_stream)
    return {"base_sha256": hashlib.sha256(Path(base).read_bytes()).hexdigest(),
            "mutated_sha256": hashlib.sha256(Path(mutated).read_bytes()).hexdigest(),
            "expected_zero": expected_zero,
            "declared_expected_zero": declared_expected_zero,
            "zero_declaration_matches": declared_expected_zero == expected_zero,
            "left_blocks": compact_left, "right_blocks": compact_right,
            "operations": ops}


def freeze(corpus: str | Path, output: str | Path | None = None) -> tuple[dict, str]:
    root = Path(corpus); manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8")); result = {"schema_version": "contract-compare-gold-v1", "manifest_sha256": hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest(), "pairs": []}
    for item in manifest.get("mutations", []):
        result["pairs"].append({"base_id": item["base_id"], "label": item["label"], "split": item["split"],
                                 "kind": item["kind"], "gold": gold_pair(item["base_path"], item["path"], expected_zero=item.get("expected_zero", False))})
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)
    target = Path(output) if output else root / "gold.json"; target.write_text(payload + "\n", encoding="utf-8")
    digest = hashlib.sha256(payload.encode()).hexdigest(); target.with_suffix(target.suffix + ".sha256").write_text(digest + "\n", encoding="utf-8")
    return result, digest


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("corpus", type=Path); parser.add_argument("--output", type=Path); args = parser.parse_args(); result, digest = freeze(args.corpus, args.output)
    print(json.dumps({"pairs": len(result["pairs"]), "sha256": digest}, ensure_ascii=False))


if __name__ == "__main__": main()
