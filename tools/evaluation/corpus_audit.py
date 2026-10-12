"""Independent read-only namespace-aware DOCX census; no model or conversion."""
from pathlib import Path
from collections import Counter
from hashlib import sha256
import argparse, json, re, sys, zipfile, time
from lxml import etree
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fundlex.docx import inspect_docx, DocxError, NS, Q

def main():
    cli=argparse.ArgumentParser(); cli.add_argument('--source',default='funds_word'); cli.add_argument('--output',default='var/evaluation/structure_audit.json'); cli.add_argument('--census-only',action='store_true');cli.add_argument('--metadata-only',action='store_true'); args=cli.parse_args()
    if args.metadata_only:
        audit=json.loads(Path(args.output).read_text(encoding='utf-8'))
        static=[r for r in audit['rows'] if r['parser_has_toc'] and r['toc_fields']==0]
        positive=[r for r in audit['rows'] if r['toc_fields']>0][:2];rows=[]
        for r in static+positive:
            path=Path(args.source)/r['file'];before=sha256(path.read_bytes()).hexdigest();inspection=inspect_docx(path,full=True)
            rows.append({'file':r['file'],'xml_toc_fields':r['toc_fields'],'directory_labels':r['directory_labels'],'early_parser_has_toc':r['parser_has_toc'],'current_parser_has_toc_field':inspection.has_toc_field,'expected':r['toc_fields']>0,'pass':inspection.has_toc_field==(r['toc_fields']>0),'source_sha256':before,'source_unchanged':before==sha256(path.read_bytes()).hexdigest(),'zone_counts_unchanged':r['zones']==dict(Counter(p.zone for p in inspection.paragraphs))})
        fixture=Path('var/evaluation/word_fixture/source.docx');fixture_inspection=inspect_docx(fixture,full=True)
        result={'static_directory_cases':len(static),'field_positive_cases':len(positive),'all_passed':all(r['pass'] and r['source_unchanged'] and r['zone_counts_unchanged'] for r in rows),'fixture_source_sha256':fixture_inspection.source_sha256,'fixture_has_toc_field':fixture_inspection.has_toc_field,'scope':'Metadata-only revalidation after true-TOC flag correction; earlier full protection audit retained','rows':rows}
        Path(args.output).with_name('toc_metadata_revalidation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=False));return
    files=sorted(Path(args.source).glob('*.docx')); rows=[]; counts=Counter(); errors=Counter(); started=time.time()
    for n,path in enumerate(files,1):
        before=sha256(path.read_bytes()).hexdigest()
        with zipfile.ZipFile(path) as z:
            root=etree.fromstring(z.read('word/document.xml'),etree.XMLParser(resolve_entities=False,no_network=True,load_dtd=False))
            toc=root.xpath('//w:instrText[contains(., "TOC")]|//w:fldSimple[contains(@w:instr,"TOC")]',namespaces=NS)
            tables=root.xpath('//w:tbl',namespaces=NS)
            fee_tables=[t for t in tables if any(key in re.sub(r'\s+','',''.join(t.xpath('.//w:t/text()',namespaces=NS))) for key in ('申购费','赎回费','销售服务费','管理费','费率'))]
            boxes=root.xpath('//w:txbxContent',namespaces=NS)
            directories=[p for p in root.xpath('//w:p',namespaces=NS) if re.fullmatch(r'\s*目\s*录\s*',''.join(p.xpath('.//w:t/text()',namespaces=NS)))]
            protected_field_nodes=set();field_depth=0
            for node in root.iter():
                if node.tag==Q('fldChar'):
                    kind=node.get(Q('fldCharType'))
                    if kind=='begin':field_depth+=1
                    elif kind=='end':field_depth=max(0,field_depth-1)
                if node.tag==Q('t') and (field_depth or any(a.tag in {Q('sdt'),Q('fldSimple')} for a in node.iterancestors())): protected_field_nodes.add(node)
            row={'file':path.name,'sha256_before':before,'toc_fields':len(toc),'directory_labels':len(directories),'tables':len(tables),'fee_tables':len(fee_tables),'textboxes':len(boxes)}
        for key in ('toc_fields','directory_labels','tables','fee_tables','textboxes'):
            counts[key+'_files']+=bool(row[key]); counts[key+'_occurrences']+=row[key]
        try:
            if args.census_only: raise DocxError('NOT_RUN_CENSUS_ONLY')
            inspection=inspect_docx(path,full=True)
            row['parser_status']='ok'; row['parser_has_toc']=inspection.has_toc_field
            row['zones']=dict(Counter(p.zone for p in inspection.paragraphs))
            # Resolve projected locations against XML independently: textbox descendants must never be writable.
            writable_box=[]; writable_toc=[];writable_field=[]
            for p in inspection.paragraphs:
                if p.zone=='toc' and p.editable: writable_toc.append(p.location)
                if p.editable:
                    for segment in p.segments:
                        for nodepath in segment.node_paths:
                            for node in root.xpath(nodepath,namespaces=NS):
                                if any(a.tag==Q('txbxContent') for a in node.iterancestors()): writable_box.append(p.location)
                                if node in protected_field_nodes: writable_field.append(p.location)
                                if any(a in directories for a in node.iterancestors(Q('p'))):writable_toc.append(p.location)
            row['writable_textbox_locations']=writable_box; row['writable_toc_locations']=writable_toc;row['writable_field_or_sdt_locations']=writable_field
            counts['parser_ok']+=1; counts['parser_has_toc_files']+=inspection.has_toc_field;counts['textbox_protection_failures']+=bool(writable_box); counts['toc_protection_failures']+=bool(writable_toc);counts['field_or_sdt_protection_failures']+=bool(writable_field)
        except DocxError as exc:
            row['parser_status']=exc.code; errors[exc.code]+=1
        row['sha256_after']=sha256(path.read_bytes()).hexdigest(); row['source_unchanged']=before==row['sha256_after']; counts['source_changed']+=not row['source_unchanged']; rows.append(row)
        if n%25==0:
            progress=Path(args.output).with_suffix('.progress.json');progress.parent.mkdir(parents=True,exist_ok=True)
            try: progress.write_text(json.dumps({'completed':n,'total':len(files),'counts':dict(counts),'parser_errors':dict(errors)},ensure_ascii=False),encoding='utf-8')
            except PermissionError: pass  # Reader/antivirus locks must not abort a read-only corpus audit.
        if n%25==0: print(f'{n}/{len(files)} elapsed={time.time()-started:.1f}s',flush=True)
    result={'files':len(files),'counts':dict(counts),'parser_errors':dict(errors),'all_sources_unchanged':all(r['source_unchanged'] for r in rows),'historical_comparison':{'toc_501':counts['toc_fields_files']==501,'fee_tables_20':counts['fee_tables_files']==20,'textboxes_7':counts['textboxes_files']==7},'fee_table_definition':'Descendant w:t joined and whitespace removed; any of 申购费/赎回费/销售服务费/管理费/费率; includes nested tables; files counted once.','rows':rows,'elapsed_seconds':round(time.time()-started,2),'no_model_calls':True,'scope':'DOCX only; read only; no conversion','parser_run':not args.census_only}
    output=Path(args.output); output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=False))
if __name__=='__main__': main()
