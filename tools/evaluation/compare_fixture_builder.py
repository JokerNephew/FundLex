"""Build a deterministic contract-comparison evaluation corpus.

The corpus is deliberately generated from the public contract collection rather
than from hand-written toy paragraphs.  Source documents are copied to a
temporary/output directory and never modified in place.  ``manifest.json`` is
the frozen gold input for :mod:`compare_evaluate` and includes source hashes,
mutation metadata and the exact target block context.

Usage::

    .venv/bin/python tools/evaluation/compare_fixture_builder.py \
        --output /tmp/fundlex-compare-corpus --count 20
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
Q = lambda name: f"{{{W}}}{name}"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _xml_parts(path: Path) -> tuple[dict[str, bytes], etree._Element]:
    with zipfile.ZipFile(path) as package:
        parts = {name: package.read(name) for name in package.namelist()}
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    return parts, etree.fromstring(parts["word/document.xml"], parser)


def _supported_source(path: Path) -> bool:
    try:
        _, root = _xml_parts(path)
        return not any(node.tag in {Q("ins"), Q("del"), Q("moveFrom"), Q("moveTo")} for node in root.iter())
    except (OSError, KeyError, zipfile.BadZipFile, etree.XMLSyntaxError):
        return False


def paragraph_text(paragraph: etree._Element) -> str:
    return "".join(node.text or "" for node in paragraph.iter(Q("t")))


def body_paragraphs(root: etree._Element) -> list[etree._Element]:
    body = root.find(f".//{Q('body')}")
    if body is None:
        return []
    return list(body.iter(Q("p")))


def _write_parts(path: Path, parts: dict[str, bytes], root: etree._Element) -> None:
    parts["word/document.xml"] = etree.tostring(root, xml_declaration=True,
                                                    encoding="UTF-8", standalone=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as package:
        for name in sorted(parts):
            package.writestr(name, parts[name])


def _set_paragraph_text(paragraph: etree._Element, text: str) -> None:
    ppr = paragraph.find(Q("pPr"))
    for child in list(paragraph):
        if child is not ppr:
            paragraph.remove(child)
    run = etree.SubElement(paragraph, Q("r"))
    text_node = etree.SubElement(run, Q("t"))
    if text[:1].isspace() or text[-1:].isspace():
        text_node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    text_node.text = text


def _new_paragraph(text: str, template: etree._Element | None = None) -> etree._Element:
    result = etree.Element(Q("p"))
    if template is not None and template.find(Q("pPr")) is not None:
        result.append(copy.deepcopy(template.find(Q("pPr"))))
    _set_paragraph_text(result, text)
    return result


def _target(paragraphs: list[etree._Element], *, minimum: int = 18,
            skip: set[int] | None = None) -> tuple[int, etree._Element, str]:
    skip = skip or set()
    candidates = [(i, p, paragraph_text(p)) for i, p in enumerate(paragraphs)
                  if i not in skip and len(paragraph_text(p).strip()) >= minimum]
    if not candidates:
        raise ValueError("base document has no suitable paragraph")
    # Prefer a normal body paragraph away from the title/contents pages.  The
    # stable candidate index keeps corpus regeneration reproducible.
    i, p, text = candidates[len(candidates) // 3]
    return i, p, text


def _context(paragraphs: list[etree._Element], index: int) -> dict:
    text = paragraph_text(paragraphs[index])
    all_same = [i for i, p in enumerate(paragraphs) if paragraph_text(p) == text]
    return {"ordinal": index, "text": text, "occurrence": all_same.index(index),
            "before_context": paragraph_text(paragraphs[index - 1])[:120] if index else "",
            "after_context": paragraph_text(paragraphs[index + 1])[:120] if index + 1 < len(paragraphs) else ""}


def _change(path: Path, kind: str, mutate, *, label: str, seed: int = 0) -> dict:
    parts, root = _xml_parts(path)
    before_paragraphs = body_paragraphs(root)
    if not before_paragraphs:
        raise ValueError(f"empty document: {path}")
    rng = random.Random(seed)
    info = mutate(root, before_paragraphs, rng)
    output = path.parent / f"{path.stem}__{label}.docx"
    _write_parts(output, parts, root)
    after_paragraphs = body_paragraphs(root)
    info.update({"kind": kind, "label": label,
                 "source_sha256": sha256(path), "mutated_sha256": sha256(output),
                 "target_after": _context(after_paragraphs, info["after_ordinal"])
                                 if info.get("after_ordinal") is not None else None})
    return {"path": str(output), **info}


def _replace_token(root, paragraphs, rng, old: str, new: str):
    candidates = [(i, p, paragraph_text(p)) for i, p in enumerate(paragraphs)
                  if old in paragraph_text(p) and len(paragraph_text(p)) > 20]
    if not candidates:
        i, p, text = _target(paragraphs)
        old, new = text[:2], new
    else:
        i, p, text = candidates[len(candidates) // 3]
    replaced = text.replace(old, new, 1)
    _set_paragraph_text(p, replaced)
    return {"target_before": _context(paragraphs, i), "before_text": old,
            "after_text": new, "after_ordinal": i}


def _insert_phrase(root, paragraphs, rng):
    i, p, text = _target(paragraphs)
    marker = "新增每日披露信息"
    at = max(1, len(text) // 2)
    _set_paragraph_text(p, text[:at] + marker + text[at:])
    return {"target_before": _context(paragraphs, i), "before_text": "",
            "after_text": marker, "after_ordinal": i}


def _delete_phrase(root, paragraphs, rng):
    candidates = [(i, p, paragraph_text(p)) for i, p in enumerate(paragraphs)
                  if "法律法规" in paragraph_text(p) and len(paragraph_text(p)) > 30]
    i, p, text = candidates[len(candidates) // 3] if candidates else _target(paragraphs)
    phrase = "法律法规另有规定的除外" if "法律法规另有规定的除外" in text else text[max(0, len(text)//3):max(0, len(text)//3)+4]
    _set_paragraph_text(p, text.replace(phrase, "", 1))
    return {"target_before": _context(paragraphs, i), "before_text": phrase,
            "after_text": "", "after_ordinal": i}


def _paragraph_insert(root, paragraphs, rng):
    i, p, text = _target(paragraphs)
    marker = "本条为对比评测新增的独立合同条款。"
    p.addnext(_new_paragraph(marker, p))
    return {"target_before": _context(paragraphs, i), "before_text": "",
            "after_text": marker, "after_ordinal": i + 1}


def _paragraph_delete(root, paragraphs, rng):
    i, p, text = _target(paragraphs)
    marker = text
    parent = p.getparent(); parent.remove(p)
    return {"target_before": {**_context(paragraphs, i), "text": marker},
            "before_text": marker, "after_text": "", "after_ordinal": None}


def _adjacent_modify(root, paragraphs, rng):
    i, p, text = _target(paragraphs)
    j = next((k for k in range(i + 1, len(paragraphs)) if len(paragraph_text(paragraphs[k])) > 18), None)
    if j is None:
        j = max(0, i - 1)
    old1 = "应当" if "应当" in text else text[:2]
    new1 = "可以" if old1 == "应当" else "修改"
    text2 = paragraph_text(paragraphs[j]); old2 = "不得" if "不得" in text2 else text2[:2]
    new2 = "可以" if old2 == "不得" else "调整"
    _set_paragraph_text(p, text.replace(old1, new1, 1)); _set_paragraph_text(paragraphs[j], text2.replace(old2, new2, 1))
    return {"target_before": _context(paragraphs, i), "before_text": old1 + " | " + old2,
            "after_text": new1 + " | " + new2, "after_ordinal": i}


def _split(root, paragraphs, rng):
    i, p, text = _target(paragraphs)
    cut = max(1, len(text) // 2)
    p1, p2 = _new_paragraph(text[:cut], p), _new_paragraph(text[cut:], p)
    parent = p.getparent(); parent.replace(p, p1); p1.addnext(p2)
    return {"target_before": {**_context(paragraphs, i), "text": text}, "before_text": text,
            "after_text": text, "after_ordinal": i, "expected_zero": True}


def _merge(root, paragraphs, rng):
    i, p, text = _target(paragraphs)
    j = next((k for k in range(i + 1, len(paragraphs)) if len(paragraph_text(paragraphs[k])) > 8), None)
    if j is None: j = i + 1
    if j >= len(paragraphs): raise ValueError("no adjacent paragraph")
    other = paragraphs[j]; joined = text + paragraph_text(other)
    _set_paragraph_text(p, joined); other.getparent().remove(other)
    return {"target_before": {**_context(paragraphs, i), "text": text + " | " + paragraph_text(other)},
            "before_text": text + paragraph_text(other), "after_text": joined,
            "after_ordinal": i, "expected_zero": True}


def _run_split(root, paragraphs, rng):
    i, p, text = _target(paragraphs)
    run = next((node for node in p.iter(Q("r")) if node.find(Q("t")) is not None and (node.find(Q("t")).text or "")), None)
    if run is None: raise ValueError("no text run")
    node = run.find(Q("t")); value = node.text or ""; cut = max(1, len(value) // 2)
    node.text = value[:cut]
    clone = copy.deepcopy(run); clone.find(Q("t")).text = value[cut:]
    run.addnext(clone)
    return {"target_before": _context(paragraphs, i), "before_text": text,
            "after_text": text, "after_ordinal": i, "expected_zero": True}


def _format_only(root, paragraphs, rng):
    i, p, text = _target(paragraphs)
    run = next((node for node in p.iter(Q("r")) if node.find(Q("t")) is not None), None)
    if run is None: raise ValueError("no text run")
    rpr = run.find(Q("rPr"))
    if rpr is None: rpr = etree.Element(Q("rPr")); run.insert(0, rpr)
    etree.SubElement(rpr, Q("b"))
    return {"target_before": _context(paragraphs, i), "before_text": text,
            "after_text": text, "after_ordinal": i, "expected_zero": True}


def _space_only(root, paragraphs, rng):
    candidates = [(i, p, paragraph_text(p)) for i, p in enumerate(paragraphs) if " " in paragraph_text(p)]
    if not candidates: raise ValueError("base has no horizontal whitespace")
    i, p, text = candidates[len(candidates)//3]; _set_paragraph_text(p, text.replace(" ", "  ", 1))
    return {"target_before": _context(paragraphs, i), "before_text": text,
            "after_text": text.replace(" ", "  ", 1), "after_ordinal": i, "expected_zero": True}


def _duplicate(root, paragraphs, rng):
    i, p, text = _target(paragraphs)
    p.addnext(copy.deepcopy(p))
    return {"target_before": _context(paragraphs, i), "before_text": "",
            "after_text": text, "after_ordinal": i + 1}


def _split_edit(root, paragraphs, rng):
    candidates = [(i,p,paragraph_text(p)) for i,p in enumerate(paragraphs) if re.search(r'\d+[.]\d+%', paragraph_text(p))]
    i,p,value = candidates[len(candidates)//2] if candidates else _target(paragraphs)
    m = re.search(r'\d+[.]\d+%', value)
    before = m.group(0) if m else value[:2]
    after = '0.30%' if before != '0.30%' else '0.31%'
    new = value.replace(before, after, 1); cut = max(1, len(new)//2)
    p1,p2 = _new_paragraph(new[:cut],p),_new_paragraph(new[cut:],p)
    p.getparent().replace(p,p1);p1.addnext(p2)
    return {'target_before': {'ordinal':i,'text':value},'before_text':before,'after_text':after,'after_ordinal':i}


def _table_cell_modify(root, paragraphs, rng):
    table = root.find(f'.//{Q("tbl")}')
    if table is None: raise ValueError('no table')
    candidate = next((p for p in table.iter(Q('p')) if paragraph_text(p).strip()), None)
    if candidate is None: raise ValueError('no table text')
    value=paragraph_text(candidate); before=value[:1]; after='更' if before!='更' else '改'
    i=paragraphs.index(candidate);_set_paragraph_text(candidate,after+value[1:])
    return {'target_before':{'ordinal':i,'text':value},'before_text':before,'after_text':after,'after_ordinal':i}


def _table_row_insert(root, paragraphs, rng):
    table = root.find(f".//{Q('tbl')}")
    if table is None: raise ValueError("base has no table")
    rows = table.findall(Q("tr"));
    if not rows: raise ValueError("table has no row")
    row = copy.deepcopy(rows[min(1, len(rows)-1)]); table.append(row)
    text = "".join(paragraph_text(p) for p in row.iter(Q("p")))
    return {"target_before": {"ordinal": None, "text": ""}, "before_text": "",
            "after_text": text, "after_ordinal": None}


def _table_row_delete(root, paragraphs, rng):
    table = root.find(f".//{Q('tbl')}"); rows = table.findall(Q("tr")) if table is not None else []
    if len(rows) < 2: raise ValueError("base table has <2 rows")
    row = rows[-1]; text = "".join(paragraph_text(p) for p in row.iter(Q("p"))); table.remove(row)
    return {"target_before": {"ordinal": None, "text": text}, "before_text": text,
            "after_text": "", "after_ordinal": None}


def _large_insert(root, paragraphs, rng):
    i, p, text = _target(paragraphs); marker = [f"新增连续条款第{k}段。" for k in range(1, 4)]
    previous = p
    for line in marker: previous.addnext(_new_paragraph(line, p)); previous = previous.getnext()
    return {"target_before": _context(paragraphs, i), "before_text": "", "after_text": "\n".join(marker), "after_ordinal": i + 1}


def _large_delete(root, paragraphs, rng):
    i, p, text = _target(paragraphs); removed = []
    for q in paragraphs[i:i+3]:
        if q.getparent() is not None: removed.append(paragraph_text(q)); q.getparent().remove(q)
    return {"target_before": {**_context(paragraphs, i), "text": "\n".join(removed)}, "before_text": "\n".join(removed), "after_text": "", "after_ordinal": None}


MUTATIONS = [
    ("modify_percent", lambda r,p,g: _replace_token(r,p,g,"0.40%","0.30%")),
    ("modify_number", lambda r,p,g: _replace_token(r,p,g,"10日","15日")),
    ("modify_negation", lambda r,p,g: _replace_token(r,p,g,"不得","可以")),
    ("modify_chinese", lambda r,p,g: _replace_token(r,p,g,"应当","可以")),
    ("modify_punctuation", lambda r,p,g: _replace_token(r,p,g,"。","；")),
    ("phrase_insert", _insert_phrase), ("phrase_delete", _delete_phrase),
    ("paragraph_insert", _paragraph_insert), ("paragraph_delete", _paragraph_delete),
    ("adjacent_modify", _adjacent_modify), ("split", _split), ("merge", _merge),
    ("run_split", _run_split), ("format_only", _format_only), ("space_only", _space_only),
    ("duplicate_paragraph", _duplicate), ("table_row_insert", _table_row_insert),
    ("table_row_delete", _table_row_delete), ("large_insert", _large_insert),
    ("large_delete", _large_delete), ("split_actual_edit", _split_edit),
    ("table_cell_modify", _table_cell_modify),
]


def build(output: Path, *, count: int = 20, seed: int = 20261023) -> dict:
    # Keep the corpus builder relocatable with the checked-out project.  A
    # previous handoff referenced a retired /home/opencode/data location.
    source_root = Path(__file__).resolve().parents[2] / "funds_word"
    sources = [p for p in sorted(source_root.glob("*.docx")) if _supported_source(p)]
    if len(sources) < count:
        raise SystemExit(f"need {count} source contracts, found {len(sources)}")
    output.mkdir(parents=True, exist_ok=True)
    # Spread the cohort across the source inventory to cover ETF, bond, mixed,
    # QDII, FOF and money-market document families instead of taking an
    # alphabetical cluster of near-identical ETF contracts.
    selected = [sources[round(i * (len(sources)-1) / (count-1))] for i in range(count)] if count > 1 else sources[:1]
    records = []
    for index, source in enumerate(selected):
        base_dir = output / f"base-{index:02d}"
        base_dir.mkdir(parents=True, exist_ok=True)
        base = base_dir / source.name
        shutil.copy2(source, base)
        base_record = {"id": f"B{index:02d}", "filename": source.name, "path": str(base),
                       "sha256": sha256(base), "split": "dev" if index < round(count * .7) else "holdout"}
        records.append(base_record)
        for mutation_index, (label, fn) in enumerate(MUTATIONS):
            try:
                item = _change(base, label, fn, label=label, seed=seed + index * 100 + mutation_index)
            except ValueError:
                continue
            item.update({"base_id": base_record["id"], "base_path": str(base),
                         "split": base_record["split"]})
            records.append(item)
    manifest = {"schema_version": "contract-compare-corpus-v1", "seed": seed,
                "count": count, "dev_count": round(count * .7),
                "holdout_count": count - round(count * .7), "bases": [r for r in records if r.get("id")],
                "mutations": [r for r in records if r.get("kind")]}
    payload = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode()
    (output / "manifest.json").write_bytes(payload)
    (output / "manifest.sha256").write_text(hashlib.sha256(payload).hexdigest() + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=20); parser.add_argument("--seed", type=int, default=20261023)
    args = parser.parse_args(); manifest = build(args.output, count=args.count, seed=args.seed)
    print(json.dumps({"bases": len(manifest["bases"]), "mutations": len(manifest["mutations"]),
                      "dev": manifest["dev_count"], "holdout": manifest["holdout_count"],
                      "manifest_sha256": (args.output / "manifest.sha256").read_text().strip()}, ensure_ascii=False))


if __name__ == "__main__": main()
