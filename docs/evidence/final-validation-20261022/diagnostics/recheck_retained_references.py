"""Read-only, zero-network repro for retained-plan reference regression fixes."""
from __future__ import annotations
import collections
import json
from pathlib import Path
import subprocess
import sys
import tempfile

REPO = next(parent for parent in Path(__file__).resolve().parents if (parent / 'fundlex/recall.py').is_file())
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'tests'))
import httpx
from fundlex import recall
from fundlex.model import ModelGateway
from fundlex.obligations import compile_obligations, apply_facts
from test_recovery_final_invariants import _inspection
from test_recall_core import _facts

attempts = []
def forbidden(*args, **kwargs):
    attempts.append('network')
    raise AssertionError('TEST_REVIEW_NETWORK_FORBIDDEN')
httpx.Client.send = forbidden
httpx.AsyncClient.send = forbidden
ModelGateway.from_env = forbidden
class Gateway:
    call = forbidden

def main():
    facts = _facts()
    source = _inspection(Path(tempfile.mkdtemp(prefix='fundlex-reference-review-')),
                         '旧业务甲句。旧业务乙句。保留句。', '另一条旧业务内容。')
    location = source.paragraphs[0].location
    before = source.paragraphs[0].text
    rule = {'rule_id': 'G99', 'operations': [
        {'op': 'replace', 'old_text': '旧业务甲句。', 'new_text': '新业务甲句。',
         'group_kind': 'INDEPENDENT', 'condition': {'kind': 'none'}},
        {'op': 'delete', 'old_text': '旧业务乙句。',
         'group_kind': 'INDEPENDENT', 'condition': {'kind': 'none'}}]}
    obligations = compile_obligations({'groups': [rule]})
    apply_facts(obligations, facts)
    targets = [recall.Target(f'T{i}', 'G99', location, before, 'needs_edit', '',
        start=0, end=len(before), segment_ok=True, resolution='resolved',
        operations=(f'G99:{i}',)) for i in range(2)]
    original = recall.plan_edits({'G99': rule}, targets, source, facts, Gateway(),
                                obligations=obligations)
    assert original['edits'][0]['content_source'] == 'atomic_paragraph'
    atomic = recall.replan_sites(original, set(), {'G99': rule}, targets[:1], source,
        facts, Gateway(), max_compose_calls=0, obligations=obligations)
    ids = [entry['target_id'] for entry in atomic['ledger']]
    assert atomic['edits'] == []
    assert len(ids) == len(set(ids)) == 2
    assert all(entry.get('reason') == 'RECALL_PLAN_REFERENCE_UNBOUND'
               and entry['status'] == 'unresolved' for entry in atomic['ledger'])
    metadata = dict(rule_id='G99', location=location, start=0, end=len(before),
                    operation_keys=['G99:0'], quote=before)
    existing = {'edits': [], 'ledger': [dict(metadata, target_id='Old',
        status='unresolved', reason='RECALL_EDIT_OVERLAP')],
        'conflicts': [{'code': 'RECALL_EDIT_OVERLAP', 'location': location,
                       'targets': ['Old'], 'spans': [[0, len(before)]]}], 'covered': []}
    current = recall.Target('New', 'G99', location, before, 'needs_edit', '',
        start=0, end=len(before), operations=('G99:0',), resolution='resolved', segment_ok=True)
    simple = recall.replan_sites(existing, set(), {}, [current], source, facts,
                                 Gateway(), max_compose_calls=0)
    assert simple['ledger'][0]['target_id'] == 'New'
    assert simple['conflicts'][0]['targets'] == ['New']
    # The former discovery ID now belongs to another business operation and site.
    other = source.paragraphs[1]
    reused = recall.Target('Old', 'G88', other.location, other.text, 'needs_edit', '',
        start=0, end=len(other.text), operations=('G88:0',), resolution='resolved', segment_ok=True)
    cross_rule = recall.replan_sites(existing, set(), {}, [reused, current], source,
        facts, Gateway(), max_compose_calls=0)
    assert cross_rule['ledger'][0]['target_id'] == 'New'
    assert cross_rule['ledger'][0]['rule_id'] == 'G99'
    assert cross_rule['ledger'][0]['operation_keys'] == ['G99:0']
    assert cross_rule['ledger'][0]['location'] == location
    assert cross_rule['conflicts'][0]['targets'] == ['New']
    assert all('Old' not in conflict['targets'] for conflict in cross_rule['conflicts'])
    # If the legitimate operation/site disappears, preserve a global unresolved
    # conflict instead of borrowing the same serial ID from the other rule.
    missing = recall.replan_sites(existing, set(), {}, [reused], source, facts,
                                  Gateway(), max_compose_calls=0)
    assert missing['edits'] == []
    assert missing['ledger'][0]['status'] == 'unresolved'
    assert missing['ledger'][0]['reason'] == 'RECALL_PLAN_REFERENCE_UNBOUND'
    assert missing['conflicts'][0]['reference_status'] == 'RECALL_PLAN_REFERENCE_UNBOUND'
    assert all(ref.startswith('UNBOUND:') for ref in missing['conflicts'][0]['targets'])
    code = (REPO / 'fundlex/recall.py').read_text()
    replan = code[code.index('def replan_sites('):code.index('\ndef build_docx_edits(')]
    assert 'id(unit)' not in replan
    assert len(attempts) == 0
    result = {
        'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
        'runtime_state': 'uncommitted retained-reference fix; not final-SHA certification',
        'network_attempts': len(attempts),
        'atomic_unbound': {'state': 'PASS', 'executable_edits': len(atomic['edits']),
                           'ledger_rows': len(ids), 'unique_target_ids': len(set(ids))},
        'simple_conflict_remap': {'state': 'PASS', 'ledger_target': simple['ledger'][0]['target_id'],
                                  'conflict_targets': simple['conflicts'][0]['targets']},
        'cross_rule_old_id_reuse': {'state': 'PASS', 'reused_id_rule': reused.rule_id,
            'reused_id_site': reused.location, 'original_operation': 'G99:0',
            'ledger_target': cross_rule['ledger'][0]['target_id'],
            'conflict_targets': cross_rule['conflicts'][0]['targets']},
        'unbound_conflict': {'state': 'PASS', 'ledger_reason': missing['ledger'][0]['reason'],
            'conflict_reference_status': missing['conflicts'][0]['reference_status'],
            'conflict_targets': missing['conflicts'][0]['targets']},
        'position_cache_replaces_object_identity': 'PASS',
    }
    destination = Path(__file__).with_name('D01-reference-remap-edge-recheck.json')
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
