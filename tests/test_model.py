import json
import sqlite3
from pathlib import Path
import httpx
import pytest
from fundlex.model import ModelError, ModelGateway
from fundlex.model_budget import BudgetError, ModelBudget

def response(value, *, status=200):
    return httpx.Response(status,json={'model':'actual-model','choices':[{'message':{'content':json.dumps(value)}}],
        'usage':{'prompt_tokens':100,'completion_tokens':20,'total_tokens':120}})

def gateway(handler, budget=None, retries=0):
    return ModelGateway(base_url='https://model.invalid',model='test',api_key='never-log-this',
        client=httpx.Client(transport=httpx.MockTransport(handler)),budget=budget,retries=retries)

def test_extra_headers_and_user_agent_are_sent():
    seen = {}

    def handler(request):
        seen.update(request.headers)
        return response({'quote': '混合型', 'fund_type': 'ordinary'})

    model = ModelGateway(base_url='https://model.invalid', model='test', api_key='never-log-this',
                         client=httpx.Client(transport=httpx.MockTransport(handler)), retries=0,
                         extra_headers={'x-opencode-session': 'session-1'}, user_agent='fundlex/0.3.0')
    model.extract_fund_type('混合型证券投资基金')
    assert seen.get('x-opencode-session') == 'session-1'
    assert seen.get('user-agent') == 'fundlex/0.3.0'
    assert seen.get('authorization') == 'Bearer never-log-this'


def test_extra_headers_cannot_override_credentials():
    with pytest.raises(ModelError, match='MODEL_EXTRA_HEADERS_INVALID'):
        ModelGateway(base_url='https://model.invalid', model='x', api_key='x',
                     extra_headers={'Authorization': 'Bearer other'})
    with pytest.raises(ModelError, match='MODEL_EXTRA_HEADERS_INVALID'):
        ModelGateway(base_url='https://model.invalid', model='x', api_key='x',
                     extra_headers={'content-type': 'text/plain'})


def test_release_fingerprint_tracks_header_names_not_values():
    from fundlex.rules import release_runtime_context

    def build(extra):
        return ModelGateway(base_url='https://model.invalid/v1', model='test', api_key='k', extra_headers=extra)

    base = release_runtime_context(build({}), 'test')['model_transport_sha256']
    same = release_runtime_context(build({'x-opencode-session': 'a'}), 'test')['model_transport_sha256']
    rotated = release_runtime_context(build({'x-opencode-session': 'b'}), 'test')['model_transport_sha256']
    named = release_runtime_context(build({'x-other-header': 'a'}), 'test')['model_transport_sha256']
    assert same == rotated, 'session-value rotation must not invalidate a release'
    assert named != same
    assert base != same


def test_from_env_rejects_invalid_extra_headers(tmp_path, monkeypatch):
    monkeypatch.setenv('LLM_BASE_URL', 'https://model.invalid')
    monkeypatch.setenv('LLM_MODEL', 'x')
    monkeypatch.setenv('LLM_API_KEY', 'x')
    monkeypatch.setenv('FUNDLEX_MODEL_LEDGER', str(tmp_path / 'ledger.sqlite'))
    monkeypatch.setenv('FUNDLEX_MODEL_EXTRA_HEADERS_JSON', '{not json')
    with pytest.raises(ModelError, match='MODEL_EXTRA_HEADERS_INVALID'):
        ModelGateway.from_env()


def test_invalid_quote_preserves_usage_and_never_retries(tmp_path: Path):
    budget=ModelBudget(tmp_path/'ledger.sqlite',max_requests=2)
    model=gateway(lambda _:response({'quote':'invented','fund_type':'ordinary'}),budget,retries=1)
    with pytest.raises(ModelError,match='MODEL_QUOTE_MISMATCH') as error:
        model.extract_fund_type('混合型证券投资基金')
    assert model.calls==1 and len(model.events)==1
    assert error.value.metrics['total_tokens']==120
    assert budget.snapshot()['statuses']=={'failed':1}
    assert 'never-log-this' not in json.dumps(model.metrics())


def test_checkpoint_restarts_without_duplicate_usage(tmp_path):
    calls=[]
    first=gateway(lambda _: (calls.append(1) or response({'quote':'混合型','fund_type':'ordinary'})))
    first.bind_checkpoints(tmp_path/'stages',{'source':'same','engine':'same'})
    first.extract_fund_type('混合型证券投资基金')
    second=gateway(lambda _:pytest.fail('verified stage should be reused'))
    second.bind_checkpoints(tmp_path/'stages',{'source':'same','engine':'same'})
    result=second.extract_fund_type('混合型证券投资基金')
    assert result.value['quote']=='混合型' and result.attempts==0
    assert second.metrics()['http_attempts']==0 and second.metrics()['checkpoint_reuses']==1
    assert second.metrics()['total_tokens']==0 and len(calls)==1
    assert 'never-log-this' not in ''.join(p.read_text(encoding='utf-8') for p in (tmp_path/'stages').glob('*.json'))


@pytest.mark.parametrize('change',['source','engine','transport','context','corrupt','invalid_quote'])
def test_checkpoint_dependency_or_corruption_forces_fresh_response(tmp_path,change):
    calls=[]
    def handler(_):
        calls.append(1)
        return response({'quote':'混合型','fund_type':'ordinary'})
    dependencies={'source':'same','engine':'same'}
    first=gateway(handler);first.bind_checkpoints(tmp_path,dependencies)
    first.extract_fund_type('混合型证券投资基金')
    if change=='corrupt':
        next(tmp_path.glob('*.json')).write_text('broken',encoding='utf-8')
    elif change=='invalid_quote':
        from fundlex.checkpoints import ModelCheckpoints
        path=next(tmp_path.glob('*.json'));record=json.loads(path.read_text(encoding='utf-8'))
        record['body']['value']['quote']='invented'
        record['sha256']=ModelCheckpoints.digest(record['body'])
        path.write_text(json.dumps(record),encoding='utf-8')
    second=gateway(handler)
    if change=='transport':second.request_options={'thinking':{'type':'disabled'}}
    if change in {'source','engine'}:dependencies={**dependencies,change:'changed'}
    second.bind_checkpoints(tmp_path,dependencies)
    second.extract_fund_type('混合型证券投资基金。' if change=='context' else '混合型证券投资基金')
    assert len(calls)==2 and second.metrics()['http_attempts']==1
    assert second.metrics()['checkpoint_reuses']==0

def test_request_budget_shared_between_gateway_instances(tmp_path: Path):
    path=tmp_path/'ledger.sqlite'
    first=gateway(lambda _:response({'quote':'混合型','fund_type':'ordinary'}),ModelBudget(path,max_requests=1))
    second=gateway(lambda _:response({'quote':'混合型','fund_type':'ordinary'}),ModelBudget(path,max_requests=1))
    assert first.extract_fund_type('混合型证券投资基金').model=='actual-model'
    with pytest.raises(ModelError,match='MODEL_GLOBAL_CALL_BUDGET_EXCEEDED'):
        second.extract_fund_type('混合型证券投资基金')
    assert second.events==[]

def test_budget_concurrency_cost_and_expired_reservation(tmp_path: Path):
    budget=ModelBudget(tmp_path/'ledger.sqlite',max_cost_usd=.001,concurrency=1)
    first=budget.reserve(input_token_bound=100,output_token_bound=10,lease_seconds=30)
    with pytest.raises(BudgetError,match='MODEL_CONCURRENCY_LIMIT'):
        budget.reserve(input_token_bound=100,output_token_bound=10,lease_seconds=30)
    budget.finish(first,{},prompt_tokens=None,completion_tokens=None,success=False)
    with pytest.raises(BudgetError,match='MODEL_COST_BUDGET_EXCEEDED'):
        budget.reserve(input_token_bound=1000,output_token_bound=1000,lease_seconds=30)
    stale=budget.reserve(input_token_bound=1,output_token_bound=1,lease_seconds=0)
    budget.reserve(input_token_bound=1,output_token_bound=1,lease_seconds=30)
    with pytest.raises(BudgetError,match='MODEL_RESERVATION_EXPIRED'):
        budget.finish(stale,{},prompt_tokens=1,completion_tokens=1,success=True)

def test_rate_limit_retry_each_attempt_is_charged(tmp_path: Path,monkeypatch):
    monkeypatch.setattr('fundlex.model.time.sleep',lambda _:None)
    calls=[]
    def handler(_):
        calls.append(1)
        return response({'quote':'混合型','fund_type':'ordinary'},status=429 if len(calls)==1 else 200)
    model=gateway(handler,ModelBudget(tmp_path/'ledger.sqlite',max_requests=2),retries=1)
    result=model.extract_fund_type('混合型证券投资基金')
    assert result.attempts==2 and model.metrics()['rate_limit_count']==1
    assert model.budget.snapshot()['http_attempts']==2

def test_extra_keys_and_context_limit_fail_closed():
    model=gateway(lambda _:response({'quote':'混合型','fund_type':'ordinary','replacement':'danger'}))
    with pytest.raises(ModelError,match='MODEL_SCHEMA_INVALID'): model.extract_fund_type('混合型')
    with pytest.raises(ModelError,match='MODEL_CONTEXT_LIMIT'): model.extract_fund_type('x'*12001)
    assert len(model.events)==1

def test_shared_service_circuit_stops_new_requests(tmp_path: Path):
    budget=ModelBudget(tmp_path/'circuit.sqlite',max_requests=10)
    for _ in range(3):
        model=gateway(lambda _:httpx.Response(503),budget)
        with pytest.raises(ModelError,match='MODEL_RETRY_EXHAUSTED'):
            model.extract_fund_type('混合型')
    model=gateway(lambda _:pytest.fail('circuit must stop transport'),budget)
    with pytest.raises(ModelError,match='MODEL_CIRCUIT_OPEN'):
        model.extract_fund_type('混合型')
    assert budget.snapshot()['http_attempts']==3

def test_transport_options_cannot_override_evidence_and_limits():
    with pytest.raises(ModelError,match='MODEL_REQUEST_OPTIONS_INVALID'):
        ModelGateway(base_url='https://model.invalid',model='x',api_key='x',request_options={'messages':[]})

def test_ledger_failure_preserves_usage_and_keeps_reservation(tmp_path: Path,monkeypatch):
    budget=ModelBudget(tmp_path/'locked.sqlite')
    def unavailable(*args,**kwargs):raise sqlite3.OperationalError('readonly database')
    monkeypatch.setattr(budget,'finish',unavailable)
    model=gateway(lambda _:response({'quote':'混合型','fund_type':'ordinary'}),budget)
    with pytest.raises(ModelError,match='MODEL_LEDGER_UNAVAILABLE') as error:
        model.extract_fund_type('混合型')
    assert error.value.metrics['total_tokens']==120
    assert budget.snapshot()['statuses']=={'reserved':1}
