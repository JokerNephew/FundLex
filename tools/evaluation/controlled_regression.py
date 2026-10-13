"""Controlled real-model DOCX evaluation, with durable application jobs and limits."""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import time
from fastapi.testclient import TestClient
from fundlex.api import create_app
from fundlex.jobs import Worker
from fundlex.model import ModelGateway
from fundlex.pipeline import process
from fundlex.rules import load_ruleset
from fundlex.store import engine_build
from fundlex.config import local_data_dir

OWNER='offline-evaluation'
STOP_CODES={'MODEL_GLOBAL_CALL_BUDGET_EXCEEDED','MODEL_COST_BUDGET_EXCEEDED',
            'MODEL_CIRCUIT_OPEN','MODEL_CONFIG_MISSING','MODEL_HTTP_ERROR','MODEL_LEDGER_UNAVAILABLE'}

def sha(data):return hashlib.sha256(data).hexdigest()
def resource_snapshot():
    if os.name!='nt':return {'rss_bytes':None,'peak_rss_bytes':None}
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in
            ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
             'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]
    counter=Counters();counter.cb=ctypes.sizeof(counter)
    ctypes.windll.kernel32.GetCurrentProcess.restype=ctypes.c_void_p
    call=ctypes.windll.psapi.GetProcessMemoryInfo
    call.argtypes=(ctypes.c_void_p,ctypes.POINTER(Counters),wintypes.DWORD)
    if not call(ctypes.windll.kernel32.GetCurrentProcess(),ctypes.byref(counter),counter.cb):return {}
    return {'rss_bytes':counter.WorkingSetSize,'peak_rss_bytes':counter.PeakWorkingSetSize}
def write(path: Path,value):
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(temp,path)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',default='funds_word')
    parser.add_argument('--output',required=True)
    parser.add_argument('--batch-size',type=int,default=10)
    parser.add_argument('--limit',type=int)
    parser.add_argument('--expected-count',type=int)
    args=parser.parse_args()
    if not 1<=args.batch_size<=20:raise SystemExit('batch size must be 1..20')
    files=sorted(Path(args.input).glob('*.docx'))
    if args.limit:files=files[:args.limit]
    if args.expected_count is not None and len(files)!=args.expected_count:
        raise SystemExit('DOCX input count does not match registered dataset')
    root=Path(args.output).resolve();root.mkdir(parents=True,exist_ok=True)
    manifest=[{'file':str(p.resolve()),'source_sha256':sha(p.read_bytes()),'size':p.stat().st_size} for p in files]
    dataset_hash=sha(json.dumps(manifest,ensure_ascii=False,sort_keys=True).encode())
    rules=load_ruleset('v1')
    if rules.auto_write_enabled:raise SystemExit('This evaluation runner requires closed business write gates')
    gateway=ModelGateway.from_env()
    options_hash=sha(json.dumps(gateway.request_options,sort_keys=True).encode())
    protocol={'schema':'evaluation-1','dataset_sha256':dataset_hash,'document_count':len(files),
        'ruleset_version':'v1','ruleset_sha256':rules.sha256,'engine_build':engine_build(),
        'model':gateway.model,'request_options_sha256':options_hash,
        'batch_size':args.batch_size,'workers':1,'model_concurrency':gateway.budget.concurrency,
        'max_context_chars':gateway.max_context_chars,'max_output_tokens':gateway.max_completion_tokens,
        'budget':gateway.budget.snapshot(),'truth_labels_available':False,
        'quality_metrics_status':'not_computable_without_independent_labels',
        'automatic_write':False,'purpose':'offline_read_only_evaluation'}
    protocol['budget_configuration']={key:protocol['budget'][key] for key in
        ('max_http_attempts','max_cost_usd','concurrency','rates_usd_per_million')}
    # The initial ledger snapshot is preserved; resume compares fixed configuration only.
    protocol_path=root/'protocol.json'
    if protocol_path.exists():
        old=json.loads(protocol_path.read_text(encoding='utf-8'))
        keys=('dataset_sha256','ruleset_sha256','engine_build','model','request_options_sha256','batch_size','max_context_chars','max_output_tokens','budget_configuration')
        if any(old[k]!=protocol[k] for k in keys):raise SystemExit('Protocol changed: use a new evaluation run directory')
    else:
        write(protocol_path,protocol);write(root/'manifest.json',manifest)
    state_root=Path(os.environ.get('FUNDLEX_EVALUATION_STATE_DIR',str(local_data_dir()/'eval'/sha(str(root).encode())[:32])))
    app=create_app(state_root);client=TestClient(app);headers={'X-FundLex-User':OWNER}
    diagnostics=root/'diagnostics';diagnostics.mkdir(exist_ok=True)
    stopped=[]
    def processor(source,output,version):
        with ModelGateway.from_env() as model:
            report=process(source,output,version,model)
        folder=diagnostics/report['source_sha256'];folder.mkdir(exist_ok=True)
        for item in output.iterdir():
            if item.is_file():shutil.copy2(item,folder/item.name)
        write(folder/'pipeline_report.json',report)
        if report.get('error_code') in STOP_CODES:stopped.append(report['error_code'])
        if any(c.get('reason') in STOP_CODES for a in report.get('actions',[]) for c in a.get('candidates',[])):
            stopped.append('MODEL_BUDGET_OR_SERVICE_STOP')
        return report
    worker=Worker(app.state.store,processor)
    batches=[]
    existing=client.get('/api/batches',headers=headers).json()['batches']
    by_key={b.get('id'):b for b in existing}
    for offset in range(0,len(files),args.batch_size):
        group=files[offset:offset+args.batch_size]
        request_key=sha((dataset_hash+':'+str(offset)).encode())
        response=client.post('/api/batches',headers={**headers,'Idempotency-Key':request_key},
            data={'ruleset_version':'v1'},files=[('files',(p.name,p.read_bytes())) for p in group])
        response.raise_for_status();batch=response.json();bid=batch['id'];batches.append(bid)
        deadline=time.monotonic()+len(group)*180+120
        while True:
            detail=client.get(f'/api/batches/{bid}',headers=headers).json()
            if detail['status']=='completed':break
            if detail['status']=='paused' or stopped:
                write(root/'stopped.json',{'batch_id':bid,'reasons':stopped or ['BATCH_PAUSED'],'budget':gateway.budget.snapshot()})
                raise SystemExit('Evaluation stopped safely; inspect stopped.json')
            if time.monotonic()>deadline:raise SystemExit('batch execution deadline exceeded')
            if not worker.run_once():time.sleep(.5)
        records=[]
        for doc in detail['documents']:
            report=client.get(doc['report_url'],headers=headers);report.raise_for_status()
            report=report.json()
            for url in doc['downloads'].values():
                delivered=client.get(url,headers=headers);delivered.raise_for_status()
            assert doc['delivery_status']!='complete' and 'final' not in doc['downloads']
            assert report.get('edit_plan',{}).get('count',0)==0
            validation=report.get('output_validation')
            if validation:assert validation['byte_identical_to_source'] and validation['not_a_final_contract']
            records.append(report)
        write(root/f'batch_{offset//args.batch_size+1:03}.json',records)
        summary=aggregate(root,batches,gateway.budget.snapshot())
        write(root/'summary.json',summary)
        print(json.dumps({'batch':offset//args.batch_size+1,'evaluated':summary['evaluated'],
            'qualification':summary['qualification'],'http_attempts':summary['budget']['http_attempts'],
            'estimated_cost_usd':summary['budget']['estimated_cost_usd']},ensure_ascii=False),flush=True)
    unchanged=all(sha(Path(item['file']).read_bytes())==item['source_sha256'] for item in manifest)
    summary=aggregate(root,batches,gateway.budget.snapshot())
    summary.update(source_files_unchanged=unchanged,dataset_sha256=dataset_hash,
                   ruleset_sha256=rules.sha256,engine_build=protocol['engine_build'],completed=unchanged and summary['evaluated']==len(files),
                   process_resources=resource_snapshot())
    write(root/'summary.json',summary)
    lines=['# FundLex 受控 DOCX 回归','',f"- 已评测：{summary['evaluated']}/{len(files)}",
        f"- 资格：{summary['qualification']}",f"- 交付：{summary['delivery']}",
        f"- 模型 HTTP 请求：{summary['budget']['http_attempts']}",
        f"- 费用估计（非账单）：USD {summary['budget']['estimated_cost_usd']:.6f}",
        f"- 源文件未改变：{unchanged}",'- 业务自动写入关闭；没有独立真值，不能报告资格/画像/候选准确率。']
    (root/'summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    assert summary['completed']

def aggregate(root: Path,batches,budget):
    reports=[r for p in sorted(root.glob('batch_*.json')) for r in json.loads(p.read_text(encoding='utf-8'))]
    action=defaultdict(Counter);candidate=defaultdict(Counter);regions=Counter();errors=Counter();durations=[]
    tokens=Counter();profile=Counter()
    for r in reports:
        if r.get('error_code'):errors[r['error_code']]+=1
        durations.append(r.get('duration_ms',0))
        for key in ('prompt_tokens','completion_tokens','total_tokens','rate_limit_count','error_count'):
            tokens[key]+=r.get('model',{}).get(key) or 0
        p=r.get('profile') or {}
        if p:profile['resolved']+=1;profile['fee_groups_verified']+=bool(p.get('fee_groups_verified'));profile['context_truncated']+=bool(p.get('context_truncated'))
        for a in r.get('actions',[]):
            action[a['action_id']][a['status']]+=1
            for c in a['candidates']:
                candidate[a['action_id']][c['status']]+=1;regions[c['region']]+=1
    durations.sort()
    return {'evaluated':len(reports),'batch_ids':batches,
        'qualification':dict(Counter(r['qualification_status'] for r in reports)),
        'delivery':dict(Counter(r['delivery_status'] for r in reports)),
        'action_statuses':{k:dict(v) for k,v in action.items()},
        'candidate_statuses':{k:dict(v) for k,v in candidate.items()},'candidate_regions':dict(regions),
        'errors':dict(errors),'profile_coverage':dict(profile),'model_usage':dict(tokens),'budget':budget,
        'latency_ms':{'p50':statistics.median(durations) if durations else None,
                      'p95':durations[min(len(durations)-1,int(len(durations)*.95))] if durations else None,
                      'over_3_minutes':sum(x>180000 for x in durations)},
        'quality_metrics':{'qualification_accuracy':None,'profile_accuracy':None,'candidate_precision':None,
                           'candidate_recall':None,'reason':'independent_ground_truth_not_available'},
        'automatic_write_enabled':False}

if __name__=='__main__':main()
