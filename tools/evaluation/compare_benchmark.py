"""Benchmark deterministic compare processing on the frozen corpus.

The default is a process-cold benchmark: every pair is run in a fresh Python
process, so module-level caches and prior pair state cannot improve later
rows.  This does not flush the operating system page cache.
"""
from __future__ import annotations
import argparse, json, statistics, subprocess, sys, time, resource
from pathlib import Path
from fundlex.compare.text_diff import compare_docx

def _percentile(values, fraction: float):
    if not values:
        return 0
    values = sorted(values)
    return values[max(0, min(len(values) - 1, int(len(values) * fraction) - 1))]


def _warm_row(base: dict, right: str) -> dict:
    started=time.perf_counter()
    result=compare_docx(base['path'], right, left_filename=base['filename'], right_filename=Path(right).name)
    elapsed=time.perf_counter()-started
    peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
    return {'base_id':base['id'],'seconds':elapsed,'peak_bytes':peak,
            'left_bytes':Path(base['path']).stat().st_size,'right_bytes':Path(right).stat().st_size,
            'left_blocks':result.left.block_count,'right_blocks':result.right.block_count,
            'diff_count':len(result.diffs)}


def _cold_row(base: dict, right: str) -> dict:
    command = [sys.executable, str(Path(__file__).resolve()), str(Path(base['path']).parent), '--worker',
               '--base', base['path'], '--right', right, '--base-id', base['id']]
    completed = subprocess.run(command, cwd=Path(__file__).resolve().parents[2],
                               check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def run(corpus: str | Path, split: str | None = None, *, cold: bool = True) -> dict:
    root=Path(corpus); manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    bases=[b for b in manifest['bases'] if split is None or b['split']==split]
    rows=[]
    for i,b in enumerate(bases):
        candidate=next((m for m in manifest['mutations'] if m['base_id']==b['id'] and m['label']=='modify_percent'),None)
        right=candidate['path'] if candidate else b['path']
        rows.append(_cold_row(b, right) if cold else _warm_row(b, right))
    values=sorted(x['seconds'] for x in rows)
    sizes=[x['left_bytes']+x['right_bytes'] for x in rows]
    blocks=[x['left_blocks']+x['right_blocks'] for x in rows]
    peaks=[x['peak_bytes'] for x in rows]
    return {'split':split or 'all','pairs':len(rows),'mode':'process-cold' if cold else 'warm-process',
            'median_seconds':statistics.median(values) if values else 0,
            'p95_seconds':_percentile(values,.95),'max_seconds':max(values,default=0),
            'median_input_bytes':statistics.median(sizes) if sizes else 0,
            'p95_input_bytes':_percentile(sizes,.95),
            'median_blocks':statistics.median(blocks) if blocks else 0,
            'p95_blocks':_percentile(blocks,.95),
            'peak_memory_bytes':max(peaks,default=0),
            'p95_peak_memory_bytes':_percentile(peaks,.95),'rows':rows}

def main():
    p=argparse.ArgumentParser();p.add_argument('corpus',type=Path);p.add_argument('--split',choices=['dev','holdout']);p.add_argument('--output',type=Path)
    p.add_argument('--warm',action='store_true');p.add_argument('--worker',action='store_true');p.add_argument('--base');p.add_argument('--right');p.add_argument('--base-id')
    a=p.parse_args()
    if a.worker:
        base={'id':a.base_id,'path':a.base,'filename':Path(a.base).name}
        print(json.dumps(_warm_row(base,a.right),ensure_ascii=False)); return
    r=run(a.corpus,a.split,cold=not a.warm);s=json.dumps(r,ensure_ascii=False,indent=2)
    if a.output:a.output.write_text(s+'\n',encoding='utf-8')
    print(json.dumps({k:r[k] for k in ('split','pairs','mode','median_seconds','p95_seconds','max_seconds','median_input_bytes','p95_input_bytes','median_blocks','p95_blocks','peak_memory_bytes','p95_peak_memory_bytes')},ensure_ascii=False))
if __name__=='__main__':main()
