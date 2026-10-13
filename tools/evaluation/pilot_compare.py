"""Offline comparison against frozen independent labels; never imported by runtime."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile
from lxml import etree

W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
Q=lambda name:'{'+W+'}'+name


def ratio(numerator,denominator):
    return numerator/denominator if denominator else None


def source_map(path):
    with ZipFile(path) as package:
        root=etree.fromstring(package.read('word/document.xml'),
            parser=etree.XMLParser(resolve_entities=False,no_network=True))
    body=root.find(Q('body'))
    paragraphs=list(body.iter(Q('p')))
    direct={id(p):f'p{i}' for i,p in enumerate(body.findall(Q('p')))}
    table={}
    for ti,t in enumerate(body.findall(Q('tbl'))):
        for ri,row in enumerate(t.findall(Q('tr'))):
            for ci,cell in enumerate(row.findall(Q('tc'))):
                for pi,p in enumerate(cell.findall(Q('p'))):
                    table[id(p)]=f'tbl{ti}/r{ri}/c{ci}/p{pi}'
    # Retain element references so lxml does not recycle Python wrapper IDs.
    maps={}
    for index,p in enumerate(paragraphs):
        maps[index]={'text':''.join(t.text or '' for t in p.iter(Q('t'))),
                     'location':direct.get(id(p),table.get(id(p)))}
    return maps


def check_evidence(evidence,mapping):
    if 'paragraph_index' not in evidence:
        return
    text=mapping[evidence['paragraph_index']]['text']
    assert text[evidence['start']:evidence['end']]==evidence['quote'],'gold source coordinate mismatch'


def compare(root: Path):
    gold_path=root/'gold.json'
    raw=gold_path.read_bytes();gold=json.loads(raw)
    frozen=json.loads((root/'gold.freeze.json').read_text(encoding='utf-8'))
    digest=hashlib.sha256(raw).hexdigest()
    # Freeze record field names are explicitly checked by the invoking protocol.
    assert digest in json.dumps(frozen),'frozen label hash mismatch'
    reports=[r for p in sorted((root/'baseline').glob('batch_*.json'))
             for r in json.loads(p.read_text(encoding='utf-8'))]
    by_hash={r['source_sha256']:r for r in reports}
    assert len(reports)==len(gold['cases'])==16
    qualification=Counter();classes=Counter();fees=Counter()
    action_stats=defaultdict(Counter);details=[];evidence_count=0
    for case in gold['cases']:
        cid=case['case_id'];source=root/'inputs'/(cid+'.docx')
        source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
        assert source_hash==case['source_sha256']
        report=by_hash[source_hash];mapping=source_map(source)
        for evidence in case['qualification'].get('evidence',[])+case['share_classes'].get('evidence',[]):
            check_evidence(evidence,mapping);evidence_count+=1
        expected=case['qualification']['status'];actual=report['qualification_status']
        known=expected in {'eligible','excluded_by_fund_type'}
        qualification['known_cases' if known else 'unknown_cases']+=1
        if known:qualification['correct' if actual==expected else 'wrong_or_abstained']+=1
        qualification['actual_'+actual]+=1
        item={'case_id':cid,'expected_qualification':expected,'actual_qualification':actual,
              'error_code':report.get('error_code'),'profile':{},'actions':[]}
        if expected=='eligible':
            wanted=case['share_classes']['value']
            predicted=report.get('profile',{}).get('share_classes',[])
            if wanted is not None:
                classes['known_cases']+=1
                classes['exact' if sorted(wanted)==sorted(predicted) else 'missing_or_different']+=1
            item['profile'].update(expected_classes=wanted,actual_classes=predicted,
                fee_groups_verified=report.get('profile',{}).get('fee_groups_verified',False))
            observed={c['name']:c for c in report.get('profile',{}).get('classes',[])}
            fields=[]
            for cls in case.get('fees',[]):
                for field in ('subscription_fee','sales_service_fee'):
                    fact=cls.get(field,{})
                    for evidence in fact.get('evidence',[]):
                        check_evidence(evidence,mapping);evidence_count+=1
                    wanted=fact.get('value')
                    predicted=observed.get(cls['name'],{}).get(field)
                    if wanted is None:
                        fees['gold_unknown']+=1
                        continue
                    fees['known_fields']+=1
                    outcome='unknown' if predicted is None else 'correct' if predicted==wanted else 'wrong'
                    fees[outcome]+=1
                    fields.append({'name':cls['name'],'field':field,'expected':wanted,'actual':predicted,'outcome':outcome})
            item['profile']['fee_fields']=fields
        observed_actions={a['action_id']:a for a in report.get('actions',[])}
        for action in case['actions']:
            aid=action['action_id'];stats=action_stats[aid];stats['reviewed_cases']+=1
            predictions=observed_actions.get(aid,{}).get('candidates',[])
            targets=[];negatives=[];satisfied=[]
            for target in action['targets']:
                for evidence in target.get('spans',[target]):
                    check_evidence(evidence,mapping);evidence_count+=1
                if target.get('edit_supported') is False:
                    stats['unsupported_semantic_targets']+=1
                    continue
                if target.get('paragraph_index') is None:continue
                target={**target,'runtime_location':mapping[target['paragraph_index']]['location']}
                {'target':targets,'negative':negatives,'satisfied':satisfied}.get(target['label'],[]).append(target)
            stats['supported_gold_targets']+=len(targets)
            stats['explicit_negative_regions']+=len(negatives)
            stats['gold_satisfied']+=len(satisfied)
            def exact(candidate,target):
                return (candidate['location']==target['runtime_location'] and candidate['region']==target['region']
                    and candidate['char_start']==target['start'] and candidate['char_end']==target['end']
                    and candidate['quote']==target['quote'])
            located=sum(any(exact(c,t) for c in predictions if c['status']!='excluded') for t in targets)
            verified=sum(any(exact(c,t) and c.get('target_verified') is True and c.get('mapping_safe') is True
                             for c in predictions) for t in targets)
            nonexcluded=[c for c in predictions if c['status'] not in {'excluded','satisfied'}]
            matched_predictions=sum(any(exact(c,t) for t in targets) for c in nonexcluded)
            overlapping=sum(any(c['location']==t['runtime_location'] and c['region']==t['region']
                and c['char_start']<t['end'] and c['char_end']>t['start'] for c in nonexcluded) for t in targets)
            false_confirmed=sum(c.get('target_verified') is True and any(
                c['location']==n['runtime_location'] and c['char_start']<n['end'] and c['char_end']>n['start']
                for n in negatives) for c in nonexcluded)
            stats['located_gold_targets']+=located;stats['verified_gold_targets']+=verified
            stats['overlapping_gold_targets_not_exact']+=overlapping-located
            stats['candidate_proposals']+=len(nonexcluded);stats['exact_target_proposals']+=matched_predictions
            stats['confirmed_on_explicit_negative']+=false_confirmed
            stats['satisfied_correct']+=sum(any(exact(c,t) and c['status']=='satisfied' for c in predictions) for t in satisfied)
            item['actions'].append({'action_id':aid,'expected_targets':len(targets),'located':located,'verified':verified,
                'runtime_status':observed_actions.get(aid,{}).get('status','not_evaluated_after_qualification'),
                'failure_reason':observed_actions.get(aid,{}).get('failure_reason'),
                'candidates':[{'location':c['location'],'status':c['status'],'reason':c.get('reason')} for c in predictions]})
        details.append(item)
    actions={}
    for aid,stats in action_stats.items():
        actions[aid]={**stats,'location_recall':ratio(stats['located_gold_targets'],stats['supported_gold_targets']),
            'verified_target_recall':ratio(stats['verified_gold_targets'],stats['supported_gold_targets']),
            'exact_target_proposal_precision':ratio(stats['exact_target_proposals'],stats['candidate_proposals']),
            'release_quantity_sufficient':False}
    summary={'scope':16,'gold_sha256':digest,'label_method':'independent AI blind review; not externally approved business truth',
        'gold_source_evidence_checks':evidence_count,'qualification':{**qualification,
            'agreement':ratio(qualification['correct'],qualification['known_cases'])},
        'share_classes':{**classes,'exact_set_recall':ratio(classes['exact'],classes['known_cases'])},
        'fee_fields':{**fees,'coverage':ratio(fees['correct']+fees['wrong'],fees['known_fields']),
            'correct_over_known':ratio(fees['correct'],fees['known_fields']),
            'precision_when_answered':ratio(fees['correct'],fees['correct']+fees['wrong'])},
        'actions':actions,'automatic_write':False,'release_approval':False,
        'limitations':['stratified 16-case diagnostic cohort, not population accuracy',
            'Only explicitly annotated actions scored; others not evaluated',
            'No-target-found is not satisfied; unknown is not a true negative',
            'Cross-paragraph unsupported targets excluded from writable recall denominator',
            'Location matching requires exact source range; wider boundary proposals are not correct edit locations'],
        'cases':details}
    (root/'comparison.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True)
    result=compare(Path(parser.parse_args().root))
    print(json.dumps({k:v for k,v in result.items() if k!='cases'},ensure_ascii=False))
