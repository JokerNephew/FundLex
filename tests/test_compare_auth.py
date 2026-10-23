import io
from fastapi.testclient import TestClient
from fundlex.api import create_app

def test_compare_password_auth_is_owner_scoped(tmp_path, monkeypatch):
    monkeypatch.setenv('FUNDLEX_AUTH_MODE','password')
    app=create_app(tmp_path); app.state.users.create_user('alice','alice-password','Alice'); app.state.users.create_user('bob','bob-password','Bob')
    c=TestClient(app)
    a=c.post('/api/auth/login',json={'username':'alice','password':'alice-password'}).json()['token']
    b=c.post('/api/auth/login',json={'username':'bob','password':'bob-password'}).json()['token']
    payload={'name':'x','pairs':[{'client_pair_id':'p','label':'p','left':{'client_id':'l','name':'a.docx','size':1},'right':{'client_id':'r','name':'b.docx','size':1}}]}
    created=c.post('/api/compare/tasks',headers={'Authorization':f'Bearer {a}'},json=payload); assert created.status_code==201
    assert c.get('/api/compare/tasks',headers={'Authorization':f'Bearer {b}'}).json()['total']==0
    assert c.get('/api/compare/tasks/'+created.json()['id'],headers={'Authorization':f'Bearer {b}'}).status_code==404
