"""Score the frozen contract comparison corpus.

Scoring is span based: a result only receives recall credit when its block id
and offset overlap an independently extracted OOXML operation interval.  Merely
finding the changed word elsewhere in a document does not pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
import signal
import sys
from pathlib import Path

from fundlex.compare.text_diff import compare_docx
from fundlex.compare.parser import parse_compare_document


def _flat_offsets(blocks):
    offsets = {}
    cursor = 0
    for index, block in enumerate(blocks):
        offsets[index] = cursor
        cursor += int(block.get("length", len(block.get("text", ""))))
        if index + 1 < len(blocks): cursor += 1
    return offsets


def _result_spans(item, side, blocks, location_index=None):
    spans = item.get(f"{side}_spans") or ([item[side]] if item.get(side) else [])
    offsets = _flat_offsets(blocks); result=[]
    for span in spans:
        bid = span.get("block_id", "")
        try: index = int(str(bid)[1:])
        except (ValueError, TypeError): continue
        if not 0 <= index < len(blocks): continue
        result.append((index,int(span.get("start", 0)), int(span.get("end", 0))))
    return result


def _overlap(a, b):
    # Inserts/deletes can have a zero-width anchor; exact boundary is valid.
    if a[0] == a[1]: return b[0] <= a[0] <= b[1]
    return max(a[0], b[0]) < min(a[1], b[1])

def _covered(spans, target):
    """Require every character in target interval to be covered by marks."""
    if target[0] == target[1]: return any(_overlap(span, target) for span in spans)
    cursor = target[0]
    for start, end in sorted(spans):
        if end <= cursor: continue
        if start > cursor: return False
        cursor = max(cursor, end)
        if cursor >= target[1]: return True
    return cursor >= target[1]


def score_pair(pair):
    gold = pair["gold"]; left_blocks, right_blocks = gold["left_blocks"], gold["right_blocks"]
    left_doc=parse_compare_document(pair["base_path"],side='L'); right_doc=parse_compare_document(pair["path"],side='R')
    result = compare_docx(left_doc, right_doc, left_filename="left.docx", right_filename="right.docx").to_dict()
    results = result.get("diffs", [])
    covered = []; modify_classified=0
    # Coordinates are meaningful only if the independent oracle and runtime
    # cover the same source blocks.  Fail explicitly rather than score against
    # shifted ordinal positions after a parser omission.
    for independent, parsed in ((left_blocks, left_doc.blocks), (right_blocks, right_doc.blocks)):
        if len(independent) != len(parsed) or any(
            int(block['length']) != len(actual.raw_text)
            for block, actual in zip(independent, parsed)
        ):
            raise ValueError('COMPARE_GOLD_BLOCK_COVERAGE_MISMATCH')
    result_blocks={'left':[{'length':len(b.raw_text)} for b in left_doc.blocks], 'right':[{'length':len(b.raw_text)} for b in right_doc.blocks]}
    for operation in ([] if gold.get('expected_zero') else gold.get("operations", [])):
        target = {}
        for side, blocks in (("left", left_blocks), ("right", right_blocks)):
            point = operation[side];
            if point.get("start") is None: continue
            location=point.get('location') or (blocks[int(point['ordinal'])].get('location') if point.get('ordinal') is not None else None)
            offsets=_flat_offsets(blocks);start=int(point.get('start',0));end=int(point.get('end',start))
            target[side]=[(index,max(start,base)-base,min(end,base+int(blocks[index].get('length',0)))-base)
                          for index,base in offsets.items() if max(start,base)<min(end,base+int(blocks[index].get('length',0)))]
        sides_hit=set(); modify_hit=False
        for side in ('left','right'):
            if target.get(side):
                all_spans=[s for d in results for s in _result_spans(d,side,result_blocks[side])]
                if all(_covered([(a,b) for index,a,b in all_spans if index==ti],(ta,tb)) for ti,ta,tb in target[side]):sides_hit.add(side)
        for item in results:
            item_hit=set()
            for side, blocks in (("left", left_blocks), ("right", right_blocks)):
                if side in target and target[side]:
                    spans=_result_spans(item,side,result_blocks[side])
                    if all(_covered([(a,b) for index,a,b in spans if index==ti],(ta,tb)) for ti,ta,tb in target[side]):
                        item_hit.add(side)
            required={side for side,value in target.items() if value}
            if item.get('type')=='modify' and required.issubset(item_hit): modify_hit=True
        required={side for side,value in target.items() if value}
        covered.append(bool(required) and required.issubset(sides_hit))
        if operation['tag']=='replace' and modify_hit:modify_classified+=1
    expected_zero = bool(gold.get("expected_zero"))
    return {"result": result, "gold_ops": len(covered), "covered": sum(covered),
            "recall": sum(covered) / len(covered) if covered else (1.0 if not results else 0.0),
            "false_positive": expected_zero and bool(results),
            "modify": sum(1 for x in results if x.get("type") == "modify"),
            "modify_classified":modify_classified,
            "expected_modify": sum(1 for x in gold.get("operations", []) if x["tag"] == "replace") if not expected_zero else 0,
            "expected_zero": expected_zero,
            "diff_count": len(results)}


def evaluate(gold_path: str | Path, *, split: str | None = None, max_pair_seconds: float = 10.0) -> dict:
    payload = json.loads(Path(gold_path).read_text(encoding="utf-8")); root = Path(gold_path).parent
    pairs = [p for p in payload.get("pairs", []) if split is None or p.get("split") == split]
    rows = []; manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if hashlib.sha256((root / 'manifest.json').read_bytes()).hexdigest() != payload['manifest_sha256']:
        raise ValueError('COMPARE_GOLD_MANIFEST_HASH_MISMATCH')
    for pair in pairs:
        # Keep path lookup out of the gold hash: paths are generated per run.
        pair = dict(pair)
        item = next(x for x in manifest["mutations"] if x["base_id"] == pair["base_id"] and x["label"] == pair["label"])
        pair.update(base_path=item["base_path"], path=item["path"])
        for filename, expected in ((pair['base_path'], pair['gold']['base_sha256']),
                                   (pair['path'], pair['gold']['mutated_sha256'])):
            if hashlib.sha256(Path(filename).read_bytes()).hexdigest() != expected:
                raise ValueError('COMPARE_GOLD_SOURCE_HASH_MISMATCH')
        started = time.perf_counter()
        def timeout(signum,frame): raise TimeoutError('COMPARE_EVALUATION_PAIR_TIMEOUT')
        old_handler=signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,max_pair_seconds)
        try:
            row = score_pair(pair)
        except (TimeoutError, ValueError) as exc:
            operations = [] if pair['gold'].get('expected_zero') else pair['gold'].get('operations', [])
            row={'gold_ops':len(operations), 'covered':0, 'recall':0,
                 'false_positive':False,'modify':0,'modify_classified':0,
                 'expected_modify':sum(x['tag']=='replace' for x in operations),
                 'expected_zero':bool(pair['gold'].get('expected_zero')),
                 'diff_count':None,'error_code':str(exc)}
        finally:
            signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old_handler)
        row["seconds"] = time.perf_counter() - started
        row.update(base_id=pair["base_id"], label=pair["label"], split=pair["split"]); rows.append(row)
        print(f"{pair['base_id']} {pair['label']}: {row['seconds']:.3f}s {row['covered']}/{row['gold_ops']}",file=sys.stderr,flush=True)
    nonzero = [r for r in rows if r["gold_ops"]]
    return {"split": split or "all", "pairs": len(rows), "planned_pairs":len(pairs), "rows": rows,
            "error_pairs":sum(bool(r.get('error_code')) for r in rows),
            "gold_ops":sum(r['gold_ops'] for r in rows), "covered":sum(r['covered'] for r in rows),
            "expected_modify":sum(r['expected_modify'] for r in rows),
            "modify_classified":sum(r['modify_classified'] for r in rows),
            "zero_pairs":sum(r['expected_zero'] for r in rows),
            "recall": sum(r["covered"] for r in nonzero) / sum(r["gold_ops"] for r in nonzero) if nonzero else 1.0,
            "identity_false_positive": sum(r["false_positive"] for r in rows if r["gold_ops"] == 0),
            "modify_classification": sum(r["modify_classified"] for r in nonzero) / sum(r["expected_modify"] for r in nonzero) if sum(r["expected_modify"] for r in nonzero) else None,
            "median_seconds": statistics.median(r["seconds"] for r in rows) if rows else 0,
            "p95_seconds": sorted(r["seconds"] for r in rows)[max(0, int(len(rows) * .95) - 1)] if rows else 0,
            "max_seconds": max((r["seconds"] for r in rows), default=0)}

def _sig(payload):
    return json.dumps({"summary": payload.get("summary"), "diffs": payload.get("diffs", [])}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _semantic(payload, *, reverse=False):
    """Direction-normalized spans, including block coordinates and polarity."""
    rows = []
    for diff in payload.get('diffs', []):
        typ = diff.get('type')
        left = diff.get('left_spans') or ([diff['left']] if diff.get('left') else [])
        right = diff.get('right_spans') or ([diff['right']] if diff.get('right') else [])
        if reverse:
            typ = {'insert':'delete','delete':'insert'}.get(typ, typ)
            left, right = right, left
        def spans(values):
            return tuple(sorted((str(s.get('block_id',''))[1:], s.get('text',''),
                                 s.get('start'), s.get('end')) for s in values))
        rows.append((typ, spans(left), spans(right)))
    return sorted(rows)

def hard_gates(gold_path: str | Path, *, max_pair_seconds: float = 30.0) -> dict:
    """Run identity, symmetry and five-run determinism gates on 20 bases.

    Symmetry compares normalized semantic tuples, so generated IDs may differ
    while the changed character spans and insert/delete polarity must agree.
    """
    root=Path(gold_path).parent; manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8')); bases=manifest['bases']
    identity=[]; symmetry=[]; deterministic=[]; symmetry_rows=[]
    for base in bases:
        started=time.perf_counter(); result=compare_docx(base['path'],base['path']).to_dict(); identity.append(not result.get('diffs'))
        base_symmetry=[]
        for label in ('modify_percent', 'phrase_insert', 'phrase_delete'):
            mut=next((m for m in manifest['mutations'] if m['base_id']==base['id'] and m['label']==label),None)
            if not mut:
                base_symmetry.append(False)
                continue
            ab=compare_docx(base['path'],mut['path']).to_dict(); ba=compare_docx(mut['path'],base['path']).to_dict()
            passed=_semantic(ab)==_semantic(ba, reverse=True)
            base_symmetry.append(passed)
            symmetry_rows.append({'base_id':base['id'], 'label':label, 'passed':passed,
                                  'forward':_semantic(ab), 'reverse':_semantic(ba,reverse=True)})
        symmetry.append(all(base_symmetry))
    determinism_identity = []
    determinism_mutant = []
    for base in bases:
        mutant = next((m for m in manifest['mutations']
                       if m['base_id'] == base['id'] and m['label'] == 'modify_percent'), None)
        identity_signatures=[_sig(compare_docx(base['path'],base['path']).to_dict()) for _ in range(5)]
        determinism_identity.append(len(set(identity_signatures))==1)
        if mutant:
            mutant_payloads=[compare_docx(base['path'],mutant['path']).to_dict() for _ in range(5)]
            mutant_signatures=[_sig(p) for p in mutant_payloads]
            determinism_mutant.append(all(p.get('diffs') for p in mutant_payloads) and len(set(mutant_signatures))==1)
        else:
            determinism_mutant.append(False)
    deterministic = [a and b for a, b in zip(determinism_identity, determinism_mutant)]
    return {
        'identity':{'passed':sum(identity),'total':len(identity)},
        'symmetry':{'passed':sum(symmetry),'total':len(symmetry),
                    'checks_passed':sum(r['passed'] for r in symmetry_rows),
                    'checks_total':len(symmetry_rows), 'rows':symmetry_rows},
        'determinism':{'passed':sum(deterministic),'total':len(deterministic),
                       'identity_runs':{'passed':sum(determinism_identity),'total':len(determinism_identity)},
                       'mutant_runs':{'passed':sum(determinism_mutant),'total':len(determinism_mutant)}},
    }


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("gold", type=Path); parser.add_argument("--split", choices=["dev", "holdout"]); parser.add_argument("--hard-gates",action='store_true'); parser.add_argument("--output", type=Path); parser.add_argument('--max-pair-seconds',type=float,default=10.0); args = parser.parse_args()
    if args.hard_gates:
        report=hard_gates(args.gold,max_pair_seconds=args.max_pair_seconds)
        if args.output: args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({key:{k:v for k,v in value.items() if k!='rows'} for key,value in report.items()},ensure_ascii=False)); return
    report = evaluate(args.gold, split=args.split,max_pair_seconds=args.max_pair_seconds); text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output: args.output.write_text(text + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("split", "pairs", "recall", "identity_false_positive", "modify_classification", "median_seconds", "p95_seconds", "max_seconds")}, ensure_ascii=False))


if __name__ == "__main__": main()
