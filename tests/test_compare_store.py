import io, tempfile, zipfile, hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pytest
from fundlex.store import RunStore, Conflict, NotFound
from fundlex.compare.store import CompareStore


def docx_bytes(text="fixture"):
    from docx import Document
    stream = io.BytesIO()
    doc = Document()
    doc.add_paragraph(text)
    doc.save(stream)
    return stream.getvalue()


def pair(suffix='', left=None, right=None):
    left, right = left or docx_bytes("left"), right or docx_bytes("right")
    return [{'client_pair_id':'p'+suffix,'label':'P','left':{'client_id':'l'+suffix,'name':'a.docx','size':len(left)},'right':{'client_id':'r'+suffix,'name':'b.docx','size':len(right)}}]

def test_compare_store_owner_idempotency_and_batch_failure(tmp_path):
    s=CompareStore(RunStore(tmp_path)); t=s.create('alice','x',pair(),idempotency_key='k')
    assert s.create('alice','x',pair(),idempotency_key='k')['id']==t['id']
    with pytest.raises(Conflict): s.create('alice','different',pair(),idempotency_key='k')
    with pytest.raises(NotFound): s.get('bob',t['id'])
    assert s.seal('alice',t['id'])['pairs'][0]['status']=='failed'

def test_compare_store_upload_seal_claim_and_fencing(tmp_path):
    s=CompareStore(RunStore(tmp_path)); left, right = docx_bytes("left"), docx_bytes("right"); t=s.create('a','x',pair(left=left,right=right))
    for cid,name in [('l','a.docx'),('r','b.docx')]:
        s.upload('a',t['id'],[{'client_id':cid,'name':name,'data':left if cid == 'l' else right,'error_code':None}])
    sealed=s.seal('a',t['id']); assert sealed['status']=='queued'
    job=s.claim(lease_seconds=5); assert job and job['attempt']==1
    valid={'schema_version':'contract-compare-v1','left':{'sha256':hashlib.sha256(left).hexdigest()},'right':{'sha256':hashlib.sha256(right).hexdigest()},'coverage':{'status':'complete'},'summary':{'total':0,'modify':0,'insert':0,'delete':0},'diffs':[]}
    with pytest.raises(Conflict): s.finish(job['id'],job['fencing_token']-1,valid)
    s.finish(job['id'],job['fencing_token'],valid)
    assert s.get('a',t['id'])['status']=='completed'

def test_compare_claim_is_single_winner_and_result_corruption_fails_closed(tmp_path):
    s=CompareStore(RunStore(tmp_path)); left, right = docx_bytes("left"), docx_bytes("right"); t=s.create('a','x',pair(left=left,right=right))
    s.upload('a',t['id'],[{'client_id':'l','name':'a.docx','data':left,'error_code':None}, {'client_id':'r','name':'b.docx','data':right,'error_code':None}]); s.seal('a',t['id'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        claimed=list(pool.map(lambda _: s.claim(lease_seconds=5), range(2)))
    assert sum(item is not None for item in claimed)==1
    job=next(item for item in claimed if item)
    valid={'schema_version':'contract-compare-v1','left':{'sha256':hashlib.sha256(left).hexdigest()},'right':{'sha256':hashlib.sha256(right).hexdigest()},'coverage':{'status':'complete'},'summary':{'total':0,'modify':0,'insert':0,'delete':0},'diffs':[]}
    s.finish(job['id'],job['fencing_token'],valid)
    with s._connect() as db:
        row=db.execute("SELECT object_key FROM compare_artifacts WHERE pair_id=?",(job['id'],)).fetchone()
    s.store.object_path(row['object_key']).write_text('tampered',encoding='utf-8')
    with pytest.raises(Conflict): s.get_pair('a',job['id'])
