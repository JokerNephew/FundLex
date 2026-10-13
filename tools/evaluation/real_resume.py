"""Actual API/worker/model retry with one injected storage interruption."""
from pathlib import Path
import argparse
import hashlib
import json
from fastapi.testclient import TestClient
from fundlex.api import create_app
from fundlex.jobs import Worker
from fundlex.model import ModelGateway
from fundlex.pipeline import process
from tools.evaluation.real_scenarios import build_contract


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    root=Path(args.output).resolve();root.mkdir(parents=True,exist_ok=True)
    source=root/'input.docx';build_contract(source)
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    app=create_app(root/'state');client=TestClient(app)
    headers={'X-FundLex-User':'real-resume'}
    response=client.post('/api/batches',headers=headers,data={'ruleset_version':'v1'},
        files=[('files',('resume.docx',source.read_bytes()))])
    response.raise_for_status();bid=response.json()['id']
    observations=[]
    def processor(input_path,output_dir,version):
        with ModelGateway.from_env() as model:
            report=process(input_path,output_dir,version,model,checkpoint_dir=root/'checkpoints')
        observations.append(report['model'])
        if len(observations)==1:
            assert report['qualification_status']=='eligible'
            raise OSError('injected storage interruption after verified model phases')
        return report
    worker=Worker(app.state.store,processor)
    assert worker.run_once()
    detail=client.get(f'/api/batches/{bid}',headers=headers).json()
    assert detail['documents'][0]['job_status']=='retry_wait'
    with app.state.store._connect() as db:
        db.execute('UPDATE documents SET next_attempt_at=0 WHERE batch_id=?',(bid,))
    assert worker.run_once()
    detail=client.get(f'/api/batches/{bid}',headers=headers).json()
    doc=detail['documents'][0]
    report=client.get(doc['report_url'],headers=headers).json()
    assert detail['status']=='completed' and report['qualification_status']=='eligible'
    assert observations[0]['http_attempts']==2
    assert observations[1]['http_attempts']==0 and observations[1]['checkpoint_reuses']==2
    assert report['edit_plan']['validated'] and not report['edit_plan']['executable']
    assert report['output_validation']['byte_identical_to_source']
    assert 'final' not in doc['downloads'] and 'redline' not in doc['downloads']
    for url in doc['downloads'].values():
        assert client.get(url,headers=headers).status_code==200
    assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
    summary={'scenario':'real_model_stage_resume','source_unchanged':True,
        'interruption':'injected storage exception; model remains real',
        'first_attempt':observations[0],'resumed_attempt':observations[1],
        'edit_plan':report['edit_plan'],'output_validation':report['output_validation'],
        'api_report_download_verified':True,'final_delivery_withheld':True}
    (root/'acceptance.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k not in {'first_attempt','resumed_attempt','output_validation','edit_plan'}},ensure_ascii=False))


if __name__=='__main__':
    main()
