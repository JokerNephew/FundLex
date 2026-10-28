"""Freeze an unseen generalization set from funds_word without touching samples.

Selection is deterministic (name-sorted stride) and excludes every pilot source
by SHA-256. Extraction files feed an independent blind annotator; no model output
is read during selection.

Run::

    .venv\\Scripts\\python.exe -X utf8 tools\\evaluation\\select_unseen.py \\
        --pilot <pilot dir> --output <unseen dir> --count 8
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
Q = lambda name: "{" + W + "}" + name


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def paragraphs_of(path: Path) -> list[dict]:
    with ZipFile(path) as package:
        root = etree.fromstring(package.read("word/document.xml"),
                                parser=etree.XMLParser(resolve_entities=False, no_network=True))
    body = root.find(Q("body"))
    result = []
    for index, paragraph in enumerate(body.iter(Q("p"))):
        text = "".join(node.text or "" for node in paragraph.iter(Q("t")))
        result.append({"paragraph_index": index, "text": text})
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", required=True)
    parser.add_argument("--output", required=True)
    from tools.evaluation.sample_corpus import DEFAULT_SAMPLE_ROOT
    parser.add_argument("--samples", default=str(DEFAULT_SAMPLE_ROOT))
    parser.add_argument("--count", type=int, default=8)
    args = parser.parse_args()
    pilot = Path(args.pilot).resolve()
    root = Path(args.output).resolve()
    inputs = root / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    pilot_selection = json.loads((pilot / "selection.json").read_text(encoding="utf-8"))
    excluded = {item["source_sha256"] for item in pilot_selection}
    candidates = []
    for path in sorted(Path(args.samples).glob("*.docx")):
        digest = sha256_file(path)
        if digest in excluded:
            continue
        candidates.append((path, digest))
    if len(candidates) < args.count:
        raise SystemExit("not enough unseen candidates")
    stride = max(1, len(candidates) // args.count)
    chosen = [candidates[index * stride] for index in range(args.count)]
    selection = []
    for number, (path, digest) in enumerate(chosen, start=1):
        case_id = f"U{number:02d}"
        target = inputs / f"{case_id}.docx"
        target.write_bytes(path.read_bytes())
        paragraphs = paragraphs_of(target)
        (root / f"{case_id}.paragraphs.json").write_text(
            json.dumps(paragraphs, ensure_ascii=False, indent=1), encoding="utf-8")
        with (root / f"{case_id}.reading.txt").open("w", encoding="utf-8") as stream:
            for item in paragraphs:
                stream.write(f"{item['paragraph_index']}: {item['text']}\n")
        selection.append({"case_id": case_id, "input": str(target), "original_file": str(path),
                          "source_sha256": digest})
    manifest = {"schema": "fundlex-unseen-selection-v1",
                "frozen_at": datetime.now(timezone.utc).isoformat(),
                "samples_root": str(Path(args.samples).resolve()),
                "excluded_pilot_hashes": sorted(excluded), "cases": selection}
    (root / "selection.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8")
    print(json.dumps({"output": str(root), "cases": [item["case_id"] for item in selection]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
