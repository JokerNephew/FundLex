import io, json, zipfile
from fastapi.testclient import TestClient
from fundlex.api import create_app

def docx(text):
    from docx import Document
    f=io.BytesIO(); d=Document(); d.add_paragraph(text); d.save(f); return f.getvalue()

def test_compare_api_roundtrip_and_xss(tmp_path):
    a,b=docx('A <script>alert(1)</script>'),docx('B')
    c=TestClient(create_app(tmp_path)); h={'X-FundLex-User':'alice'}
    payload={'name':'cmp','pairs':[{'client_pair_id':'p','label':'P','left':{'client_id':'l','name':'a.docx','size':len(a)},'right':{'client_id':'r','name':'b.docx','size':len(b)}}]}
    created=c.post('/api/compare/tasks',headers=h,json=payload); assert created.status_code==201
    tid=created.json()['id']; c.post(f'/api/compare/tasks/{tid}/uploads',headers=h,data={'client_ids':'["l","r"]'},files=[('files',('a.docx',a)),('files',('b.docx',b))])
    c.post(f'/api/compare/tasks/{tid}/seal',headers=h); from fundlex.compare.worker import CompareWorker
    assert CompareWorker(c.app.state.compare_store).run_once(); pid=created.json()['pairs'][0]['id']
    view=c.get(f'/api/compare/pairs/{pid}/view',headers=h); assert view.status_code==200
    assert '<script>' not in view.json()['left']['html']
    assert c.get(f'/api/compare/pairs/{pid}',headers={'X-FundLex-User':'bob'}).status_code==404
