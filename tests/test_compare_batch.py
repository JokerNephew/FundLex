import io
from docx import Document
from fundlex.store import RunStore
from fundlex.compare.store import CompareStore
import hashlib

def test_failed_pair_does_not_block_other_pairs(tmp_path):
    def docx(text):
        b=io.BytesIO(); d=Document(); d.add_paragraph(text); d.save(b); return b.getvalue()
    docs=[docx('left-0'), docx('right-0'), docx('left-1'), docx('right-1')]
    s=CompareStore(RunStore(tmp_path)); pairs=[]
    for i in range(2):
        pairs.append({'client_pair_id':f'p{i}','label':str(i),'left':{'client_id':f'l{i}','name':'a.docx','size':len(docs[i*2])},'right':{'client_id':f'r{i}','name':'b.docx','size':len(docs[i*2+1])}})
    t=s.create('a','batch',pairs)
    for i in range(2):
        s.upload('a',t['id'],[{'client_id':f'l{i}','name':'a.docx','data':docs[i*2],'error_code':None},{'client_id':f'r{i}','name':'b.docx','data':docs[i*2+1],'error_code':None}])
    s.seal('a',t['id']); jobs=[]
    while (job:=s.claim()): jobs.append(job)
    assert len(jobs)==2
    valid={'schema_version':'contract-compare-v1','left':{'sha256':hashlib.sha256(docs[0]).hexdigest()},'right':{'sha256':hashlib.sha256(docs[1]).hexdigest()},'coverage':{'status':'complete'},'summary':{'total':0,'modify':0,'insert':0,'delete':0},'diffs':[]}
    s.finish(jobs[0]['id'],jobs[0]['fencing_token'],valid)
    s.finish(jobs[1]['id'],jobs[1]['fencing_token'],{'coverage':{'status':'incomplete'},'summary':{}},failed=True,error_code='COMPARE_PARSE_FAILED')
    state=s.get('a',t['id']); assert state['counts']['succeeded']==1 and state['counts']['failed']==1
