"""Generic defects reproduced by exact-HEAD live validation and independent review."""
import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import httpx
import pytest

from fundlex.model import ModelError, ModelGateway
from fundlex.recall import Target, dedupe_operation_targets, plan_target
from fundlex.generation.claim_replay import replay_claims
from fundlex.obligations import compile_obligations


def request():
    return dict(task_type='recall_inventory', bounded_context='public contract',
                response_schema={'type': 'object', 'required': ['ok']},
                instruction='extract', prompt_version='v1')


def test_record_single_flight_full_request_and_failure_replay(tmp_path):
    calls = []
    def provider(req):
        calls.append(req)
        payload = json.loads(req.content)
        if 'failure' in payload['messages'][1]['content']:
            content, reason = '{"ok":', 'length'
        else:
            content, reason = json.dumps({'ok': len(calls)}), 'stop'
        return httpx.Response(200, json={'model': 'm', 'choices': [
            {'message': {'content': content}, 'finish_reason': reason}]})
    with ModelGateway(base_url='https://example.invalid', model='m', api_key='secret',
            mode='record', cassette_dir=tmp_path, max_calls=30,
            client=httpx.Client(transport=httpx.MockTransport(provider))) as gateway:
        with ThreadPoolExecutor(max_workers=4) as pool:
            values = list(pool.map(lambda _: gateway.call(**request()).value, range(4)))
        assert values == [{'ok': 1}] * 4
        assert len(calls) == 1
        # Same context with a different instruction is a distinct full request.
        assert gateway.call(**{**request(), 'instruction': 'other'}).value == {'ok': 2}
        with pytest.raises(ModelError, match='MODEL_OUTPUT_TRUNCATED'):
            gateway.call(**{**request(), 'bounded_context': 'failure'})
        assert len(calls) == 3
    with ModelGateway(base_url='', model='m', api_key='', mode='replay', cassette_dir=tmp_path) as gateway:
        assert gateway._client is None
        assert gateway.call(**request()).value == {'ok': 1}
        with pytest.raises(ModelError, match='MODEL_OUTPUT_TRUNCATED'):
            gateway.call(**{**request(), 'bounded_context': 'failure'})
        with pytest.raises(ModelError, match='MODEL_REPLAY_MISS'):
            gateway.call(**{**request(), 'bounded_context': 'missing'})
        assert gateway.metrics()['http_attempts'] == 0


def test_role_replay_needs_models_but_no_credentials(tmp_path, monkeypatch):
    from fundlex.models.roles import build_role_gateway
    for name in list(__import__('os').environ):
        if name.startswith(('LLM_', 'FUNDLEX_PRIMARY_', 'FUNDLEX_REVIEW_', 'FUNDLEX_MODEL_')):
            monkeypatch.delenv(name)
    monkeypatch.setenv('FUNDLEX_MODEL_MODE', 'replay')
    monkeypatch.setenv('FUNDLEX_MODEL_CASSETTE_DIR', str(tmp_path))
    monkeypatch.setenv('FUNDLEX_PRIMARY_MODEL', 'm1')
    monkeypatch.setenv('FUNDLEX_REVIEW_MODEL', 'm2')
    with build_role_gateway() as gateway:
        assert gateway.primary._client is gateway.review._client is None
        assert gateway.budget is None
        for task in ('recall_facts', 'recall_audit'):
            with pytest.raises(ModelError, match='MODEL_REPLAY_MISS'):
                gateway.call(**{**request(), 'task_type': task})


class Inspection:
    def __init__(self, text):
        self.paragraphs = [SimpleNamespace(location='p0', text=text)]
    def by_location(self, _):
        return self.paragraphs[0]


def test_dedupe_keeps_disjoint_required_occurrences_and_claim_blocks_omission():
    old, new = 'A类基金份额', 'C类基金份额'
    before = '对于收取申购费的A类基金份额应披露费率。另对于收取申购费的A类基金份额应披露申购费用。'
    rule = {'rule_id': 'G02', 'class_substitution': True, 'title': '份额类别', 'operations': [
        {'op': 'replace', 'old_text': old, 'new_text': new, 'condition': {'kind': 'none'},
         'operation_id': 'G02:0', 'group_kind': 'INDEPENDENT'}]}
    a = before.index(old)
    b = before.index(old, a + 1)
    targets = [Target(f'T{i}', 'G02', 'p0', old, 'needs_edit', 'verified occurrence',
        start=p, end=p+len(old), operations=('G02:0',), occurrence_index=i,
        resolution='resolved', segment_ok=True) for i, p in enumerate((a, b))]
    source = Inspection(before)
    _, removed = dedupe_operation_targets(targets, {'G02': rule}, source)
    assert removed == []
    ledger = compile_obligations({'groups': [rule]})
    for record in ledger.records:
        record.applicability = SimpleNamespace(status='TRUE')
    edit = {'rule_id': 'G02', 'target_id': 'T0', 'location': 'p0', 'start': a,
            'end': a+len(old), 'replacement': new, 'operation_keys': ['G02:0'], 'content_source': 'guide'}
    result = replay_claims([edit], source, Inspection(before[:a]+new+before[a+len(old):]),
        rules_by_id={'G02': rule}, targets_by_id={t.target_id: t.as_dict() for t in targets}, obligations=ledger)
    assert result['verified'] is False
    assert result['failures']


@pytest.mark.parametrize('names', [('A', 'C'), ('A类', 'C类'), ('A 类', 'C 类'),
                                  ('A类基金份额', 'C类基金份额')])
def test_complete_class_set_accepts_equivalent_display_names(names):
    from fundlex.fact_evidence import verify_class_set
    quote = '本基金将基金份额分为A类、C类两种不同的类别。'
    classes = [SimpleNamespace(name=name, current=True) for name in names]
    assert verify_class_set(Inspection(quote), classes, quote)['set_complete_verified']
    classes.append(SimpleNamespace(name='E类', current=True))
    assert not verify_class_set(Inspection(quote), classes, quote)['set_complete_verified']


def test_audit_missed_second_occurrence_is_not_hidden_by_same_operation(tmp_path):
    from docx import Document
    from fundlex.docx import inspect_docx
    from fundlex.recall_pipeline import _absorb_missed_targets
    from test_operation_execution_closure import Facts
    text = '甲条旧业务。乙条旧业务。'
    path = tmp_path / 'source.docx'
    doc = Document()
    doc.add_paragraph(text)
    doc.save(path)
    source = inspect_docx(path, full=True)
    loc = source.paragraphs[0].location
    rule = {'rule_id': 'G99', 'operations': [dict(op='delete', old_text='旧业务', condition={'kind': 'none'})]}
    first = Target('T', 'G99', loc, '甲条旧业务。', 'needs_edit', '', start=0, end=6,
                   operations=('G99:0',), resolution='resolved')
    state = {'missed': {'G99': [dict(location=loc, quote='乙条旧业务。', operation_id='G99:0')]}}
    synthetic, origins = [], {}
    assert _absorb_missed_targets(state, [first], synthetic, origins, source,
                                  rules_by_id={'G99': rule}, facts=Facts()) == 1
    assert synthetic[0].start == 6
    assert _absorb_missed_targets(state, [first], synthetic, origins, source,
                                  rules_by_id={'G99': rule}, facts=Facts()) == 0


def test_g05_token_splice_keeps_coordination_punctuation():
    from test_operation_execution_closure import Facts, Inspection, rule
    text = '基金管理人可调低赎回费率或变更收费方式。'
    target = Target('T', 'G05', 'p0', text, 'needs_edit', '', start=0, end=len(text),
                    operations=('G05:0',), resolution='resolved')
    edit = plan_target(rule(), target, Inspection([text]), Facts(), None, compose_budget=[0])
    assert edit.replacement == text.replace('赎回费率', '销售服务费率')


def test_append_refuses_incomplete_cross_paragraph_clause(monkeypatch):
    from test_operation_execution_closure import Facts, Inspection
    from fundlex.recall import RecallError
    monkeypatch.setenv('FUNDLEX_GENERATION_STRATEGY', 'legacy')
    text = '基金份额类别：指本基金分设A类和C类两种不同的'
    rule = {'rule_id': 'G01', 'operations': [dict(op='append', new_text='新政策。', condition={'kind': 'none'})]}
    target = Target('T', 'G01', 'p0', text, 'needs_edit', '', start=0, end=len(text),
                    operations=('G01:0',), resolution='resolved')
    with pytest.raises(RecallError, match='RECALL_APPEND_CLAUSE_INCOMPLETE'):
        plan_target(rule, target, Inspection([text, '类别。其他内容。']), Facts(), None, compose_budget=[0])


def test_audit_model_execution_hint_cannot_route_missing_plan_to_writer():
    from fundlex.recall_pipeline import _audit_recovery_contexts
    from fundlex.recovery import FailureClass
    target = Target('T', 'G99', 'p0', '旧业务', 'needs_edit', '', start=0, end=3,
                    operations=('G99:0',), resolution='resolved')
    issue = dict(code='AUDIT_NOT_COMPLETED', rule_id='G99', target_id='T', location='p0',
                 failure_class='EXECUTION', affected_obligation='free text model guess')
    contexts = _audit_recovery_contexts([issue], targets=[target], planned={'edits': []},
        artifact_failures=[dict(code='CLAIM_OPERATION_NOT_PLANNED', operation_id='G99:0', location='p0')])
    assert contexts[0].resolved_class is FailureClass.GENERATION
    assert contexts[0].operation_id == 'G99:0'
    assert contexts[0].obligation_id != issue['affected_obligation']


def test_audit_identity_keeps_sibling_operation_negative_verdict():
    from fundlex.recall_pipeline import _merge_audit_state, _audit_issues
    targets = [Target(str(i), 'G05', 'p0', '同址旧业务句。', 'needs_edit', '', start=0, end=8,
                      operations=(f'G05:{i}',), resolution='resolved') for i in range(2)]
    state = {'results': {}, 'missed': {}}
    results = [dict(target_id=str(i), rule_id='G05', verdict=verdict,
                    evidence_verified=True, reason='verified local quote')
               for i, verdict in enumerate(('wrong', 'completed'))]
    _merge_audit_state(state, dict(rules=['G05'], results=results, missed_targets=[]), targets)
    assert len(state['results']) == 2
    issues = _audit_issues(state, targets)
    assert len(issues) == 1 and issues[0]['target_id'] == '0'


def test_recovery_snapshot_handles_bound_and_unbound_sites():
    from fundlex.recall_pipeline import _recovery_snapshot
    targets = [Target('T1', 'G99', 'p0', '旧业务', 'needs_edit', '', start=0, end=3),
               Target('T2', 'G99', 'p0', '旧业务', 'needs_edit', '')]
    state = dict(failures=[])
    one = _recovery_snapshot(targets, {'edits': []}, Inspection('旧业务'), state)
    assert one == _recovery_snapshot(list(reversed(targets)), {'edits': []}, Inspection('旧业务'), state)
    targets[1].start = 0
    assert one != _recovery_snapshot(targets, {'edits': []}, Inspection('旧业务'), state)


def test_audit_sibling_operations_route_each_own_root_cause():
    from fundlex.recall_pipeline import _audit_recovery_contexts
    from fundlex.recovery import FailureClass
    target = Target('T', 'G99', 'p0', '旧业务', 'needs_edit', '', start=0, end=3,
                    operations=('G99:0', 'G99:1'), resolution='resolved')
    issue = dict(code='AUDIT_NOT_COMPLETED', rule_id='G99', target_id='T', location='p0',
                 failure_class='EXECUTION')
    failures = [dict(code='CLAIM_OPERATION_NOT_PLANNED', operation_id='G99:0', location='p0'),
                dict(code='CLAIM_EXECUTION_EFFECT_MISSING', operation_id='G99:1', location='p0')]
    edit = dict(rule_id='G99', target_id='T', location='p0', operation_keys=['G99:1'])
    for order in (failures, list(reversed(failures))):
        contexts = _audit_recovery_contexts([issue], targets=[target], planned={'edits': [edit]},
                                           artifact_failures=order)
        assert {ctx.operation_id: ctx.resolved_class for ctx in contexts} == {
            'G99:0': FailureClass.GENERATION, 'G99:1': FailureClass.EXECUTION}
