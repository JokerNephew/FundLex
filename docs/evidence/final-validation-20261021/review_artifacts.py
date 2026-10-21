"""Independently compare source, final edit set and real DOCX paragraphs (no models)."""
from pathlib import Path
import argparse, collections, hashlib, json, re, sys, zipfile
REPO = next(parent for parent in Path(__file__).resolve().parents if (parent / 'fundlex/docx.py').is_file())
sys.path.insert(0, str(REPO))
from fundlex.docx import inspect_docx


def review(root, case):
    out = root/'artifacts'/case
    frozen = root/'frozen'/case
    report = json.loads((out/'report.json').read_text())
    records = (report.get('obligations') or {}).get('records') or []
    true = [r for r in records if (r.get('applicability') or {}).get('status') == 'TRUE']
    targets = report.get('targets') or []
    plan = (report.get('plan') or {}).get('edits') or []
    replay = report.get('artifact_claim_replay') or {}
    rows = []
    for r in true:
        spec = r.get('spec') or r
        op = spec.get('operation_id') or r.get('operation_id')
        oid = r['obligation_id']
        sites = [t for t in targets if op in (t.get('operations') or [])]
        def owns(edit):
            return (op in (edit.get('operation_keys') or []) or
                    any(owns(c) for c in edit.get('components') or []))
        own_edits = [e for e in plan if owns(e)]
        rows.append(dict(obligation_id=oid, operation_id=op, completion=r.get('completion'),
            applicability=r.get('applicability'), sites=sites, edits=own_edits,
            proof=(replay.get('obligations') or {}).get(oid),
            completion_evidence=r.get('completion_evidence')))
    actual = next((out/name for name in ('working_final.docx','final.docx') if (out/name).is_file()), None)
    result = dict(case_id=case, true_obligations=len(true),
        true_not_applicable=sum(r.get('completion') == 'NOT_APPLICABLE' for r in true),
        delivery=report.get('delivery_status'), obligations=rows,
        artifact_review='UNVERIFIED' if actual is None else 'PROGRAMMATIC_REVIEW')
    if actual is not None:
        source = inspect_docx(frozen/'original.docx',full=True)
        final = inspect_docx(actual,full=True)
        before = {p.location:p.text for p in source.paragraphs}
        after = {p.location:p.text for p in final.paragraphs}
        changed = []
        mismatches = []
        for loc in sorted(set(before)|set(after)):
            old,new = before.get(loc,''),after.get(loc,'')
            edits = [e for e in plan if e.get('location') == loc]
            expected = old
            for e in sorted(edits,key=lambda e:(int(e['start']),int(e['end'])),reverse=True):
                expected = expected[:int(e['start'])]+str(e.get('replacement') or '')+expected[int(e['end']):]
            if new != expected:
                mismatches.append(dict(location=loc, expected=expected, actual=new))
            if old != new:
                changed.append(dict(location=loc,before=old,after=new,final_edits=edits,
                    plan_matches_actual=(new == expected)))
        with zipfile.ZipFile(actual) as archive:
            xml = archive.read('word/document.xml').decode('utf-8')
        redline = next((out/name for name in ('working_redline.docx','redline.docx') if (out/name).is_file()),None)
        redline_counts = None
        if redline:
            with zipfile.ZipFile(redline) as archive:
                red_xml = archive.read('word/document.xml').decode('utf-8')
            redline_counts = dict(ins=len(re.findall(r'<w:ins(?:\s|>)',red_xml)),
                                  delete=len(re.findall(r'<w:del(?:\s|>)',red_xml)))
            from lxml import etree
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            def xml_paragraphs(path, accept=True):
                with zipfile.ZipFile(path) as archive:
                    document = etree.fromstring(archive.read('word/document.xml'))
                lines = []
                for paragraph in document.xpath('//w:body//w:p', namespaces=ns):
                    parts = []
                    for node in paragraph.xpath('.//w:t | .//w:delText', namespaces=ns):
                        if node.xpath('ancestor::w:del' if accept else 'ancestor::w:ins', namespaces=ns):
                            continue
                        parts.append(node.text or '')
                    lines.append(''.join(parts))
                return lines
            accepted, rejected = xml_paragraphs(redline), xml_paragraphs(redline, False)
            final_lines, source_lines = xml_paragraphs(actual), xml_paragraphs(frozen/'original.docx')
            redline_counts.update(accepted_matches_final=accepted == final_lines,
                                  rejected_matches_original=rejected == source_lines,
                                  accepted_paragraph_count=len(accepted), rejected_paragraph_count=len(rejected))
        result.update(artifact_file=actual.name, artifact_sha256=hashlib.sha256(actual.read_bytes()).hexdigest(),
            original_paragraph_count=len(before), final_paragraph_count=len(after),
            changed_paragraphs=changed, plan_artifact_mismatches=mismatches,
            final_revision_elements=len(re.findall(r'<w:(?:ins|del)(?:\s|>)',xml)),
            redline_revision_elements=redline_counts)
    target = root/'summaries'/f'{case}-artifact-review.json'
    target.parent.mkdir(exist_ok=True,parents=True)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return {k:v for k,v in result.items() if k not in {'obligations','changed_paragraphs'}}

if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('root',type=Path)
    p.add_argument('cases',nargs='+')
    a=p.parse_args()
    for c in a.cases:
        print(json.dumps(review(a.root,c),ensure_ascii=False))
