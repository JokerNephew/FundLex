const API = '/api';
const $ = (selector) => document.querySelector(selector);
const state = { batches: [], selected: null, detail: null, loading: false };
const statusText = {receiving:'接收中',queued:'排队中',leased:'已领取',running:'处理中',retry_wait:'等待重试',paused:'已暂停',completed:'已完成',succeeded:'已处理',failed:'失败',eligible:'符合资格',excluded_by_fund_type:'整份排除',complete:'完整',incomplete:'不完整',not_generated:'未生成',applied:'已修改',satisfied:'已符合',excluded:'非目标候选',satisfied_no_change:'已符合',not_matched:'未命中',not_applicable:'不适用',unknown:'未确认'};
const label = (value) => statusText[value] ?? value ?? '—';
const kind = (value) => ['complete','succeeded','eligible','applied','satisfied','satisfied_no_change'].includes(value) ? 'good' : ['failed'].includes(value) ? 'error' : ['incomplete','excluded_by_fund_type','retry_wait'].includes(value) ? 'warn' : ['running','leased','queued'].includes(value) ? 'active' : '';
const element = (tag, className, text) => { const e=document.createElement(tag); if(className)e.className=className; if(text!==undefined)e.textContent=String(text); return e; };
function badge(value){ const e=element('span',`badge ${kind(value)}`,label(value)); return e; }
function setNotice(message,error=false){const n=$('#notice');n.textContent=message;n.classList.toggle('error',error);n.hidden=!message;}
function identity(){return ($('#dev-user').value || '').trim();}
async function api(path,options={}){
  if(!identity()) throw new Error('请输入本地开发身份。');
  const owner=identity();
  const headers=new Headers(options.headers || {});headers.set('X-FundLex-User',owner);
  const response=await fetch(`${API}${path}`,{...options,headers});
  if(owner!==identity())throw new Error('本地身份已变更，已取消旧身份结果。');
  if(!response.ok){let description='';try{const payload=await response.json();description=typeof payload.detail==='string'?payload.detail:JSON.stringify(payload.detail || payload);}catch{description=await response.text();}throw new Error(`${response.status} ${description || response.statusText}`);}
  return response;
}
async function json(path,options){return (await api(path,options)).json();}
function batchId(batch){return batch.batch_id || batch.id;}
function documentId(doc){return doc.document_id || doc.id;}
function batchDocuments(batch){return batch.documents || batch.jobs || [];}
function batchStatus(batch){return batch.status || batch.job_status || 'queued';}
function documentStatus(doc){return doc.job_status || doc.status || 'queued';}
function qualification(doc){return doc.qualification_status || doc.eligibility_status || doc.eligibility?.status || doc.eligibility || null;}
function delivery(doc){return doc.delivery_status || doc.delivery?.status || null;}
function counts(batch){
  const docs=batchDocuments(batch),summary=batch.summary || batch.counts || {};
  return {total:summary.total ?? batch.total ?? batch.total_documents ?? batch.document_count ?? docs.length,
    finished:summary.finished ?? batch.completed ?? docs.filter(d=>['succeeded','failed'].includes(documentStatus(d))).length,
    incomplete:summary.incomplete ?? docs.filter(d=>delivery(d)==='incomplete').length,
    complete:summary.complete ?? docs.filter(d=>delivery(d)==='complete').length};
}
function setMetrics(batch){const c=batch?counts(batch):null;$('#metric-total').textContent=c?.total ?? '—';$('#metric-finished').textContent=c?.finished ?? '—';$('#metric-incomplete').textContent=c?.incomplete ?? '—';$('#metric-complete').textContent=c?.complete ?? '—';$('#metric-total-note').textContent=batch?`规则 ${batch.ruleset_version || batch.rule_version || '—'}`:'选择批次后显示';}
function renderBatches(){
  const box=$('#batch-list');box.replaceChildren();
  if(!state.batches.length){box.append(element('div','empty','尚无批次。使用“新建批次”提交 DOCX。'));return;}
  for(const batch of state.batches){
    const id=batchId(batch),button=element('button',`batch-row ${state.selected===id?'selected':''}`);button.type='button';button.setAttribute('aria-label',`查看批次 ${id}`);
    const title=element('div','batch-name',batch.name || `批次 ${id}`);title.append(element('small','batch-meta',`${id} · ${batch.created_at ? new Date(batch.created_at).toLocaleString('zh-CN') : '时间未提供'}`));
    const c=counts(batch);button.append(title,element('span','batch-count',`${c.finished} / ${c.total}`),badge(batchStatus(batch)));
    button.addEventListener('click',()=>selectBatch(id));box.append(button);
  }
}
function renderSelected(batch){
  setMetrics(batch);const box=$('#batch-status'),download=$('#batch-download');box.replaceChildren();download.replaceChildren();
  if(!batch){$('#selected-id').textContent='尚未选择';box.append(element('div','empty','选择左侧批次查看进度。'));return;}
  $('#selected-id').textContent=batchId(batch);const c=counts(batch);
  for(const [name,value] of [['执行状态',batchStatus(batch)],['规则版本',batch.ruleset_version || batch.rule_version || '—'],['处理结果',`${c.finished} / ${c.total}`],['完整交付',c.complete],['不完整',c.incomplete]]){
    const row=element('div','status-line');row.append(element('strong','',name),element('span','',label(value)));box.append(row);
  }
  const track=element('div','progress-track'),fill=element('div','progress-fill');fill.style.width=`${c.total ? Math.min(100,Math.round(c.finished/c.total*100)) : 0}%`;track.append(fill);box.append(track);
  const link=element('button','text-button','下载批次汇总 Markdown');link.type='button';link.addEventListener('click',()=>downloadFile(`/batches/${encodeURIComponent(batchId(batch))}/report`,`batch-${batchId(batch)}.md`));download.append(link);
  if(['queued','running'].includes(batchStatus(batch))){
    const pause=makeAction('暂停批次',()=>setBatchState('pause'));pause.classList.add('batch-control');download.append(pause);
  }else if(batchStatus(batch)==='paused'){
    const resume=makeAction('继续批次',()=>setBatchState('resume'));resume.classList.add('batch-control');download.append(resume);
  }
}
async function setBatchState(action){
  try{await json(`/batches/${encodeURIComponent(state.selected)}/${action}`,{method:'POST'});setNotice(action==='pause'?'批次已暂停。':'批次已继续。');await selectBatch(state.selected,{quiet:true});}
  catch(error){setNotice(`${action==='pause'?'暂停':'继续'}失败：${error.message}`,true);}
}
function makeAction(text,callback){const b=element('button','text-button',text);b.type='button';b.addEventListener('click',callback);return b;}
function renderDocuments(batch){
  const body=$('#document-rows');body.replaceChildren();const docs=batch?batchDocuments(batch):[];$('#documents-count').textContent=`${docs.length} 份`;
  if(!docs.length){const row=element('tr');const cell=element('td','empty',batch?'该批次暂无合同结果。':'选择批次查看合同。');cell.colSpan=5;row.append(cell);body.append(row);return;}
  for(const doc of docs){
    const row=element('tr'),name=element('td'),file=element('div','file-name',doc.filename || doc.original_filename || doc.name || documentId(doc));name.append(file);
    if(doc.source_sha256)name.append(element('div','file-hash',`SHA-256 ${doc.source_sha256.slice(0,16)}…`));
    const qual=element('td');qual.append(badge(qualification(doc)));const del=element('td');del.append(badge(delivery(doc)));const job=element('td');job.append(badge(documentStatus(doc)));
    const actions=element('td','actions');actions.append(makeAction('查看报告',()=>showDocument(doc)));
    row.append(name,qual,del,job,actions);body.append(row);
  }
}
async function selectBatch(id,{quiet=false}={}){
  try{const batch=await json(`/batches/${encodeURIComponent(id)}`);state.selected=id;state.batch=batch;renderBatches();renderSelected(batch);renderDocuments(batch);if(state.detail){const current=batchDocuments(batch).find(d=>documentId(d)===state.detail);if(current)showDocument(current,{quiet:true});}
    if(!quiet)$('#documents-section').scrollIntoView({behavior:'smooth',block:'nearest'});
  }catch(error){if(!quiet)setNotice(`读取批次失败：${error.message}`,true);}
}
async function refresh({quiet=false}={}){
  if(state.loading)return;state.loading=true;
  try{const payload=await json('/batches');state.batches=Array.isArray(payload)?payload:(payload.batches || payload.items || []);renderBatches();if(state.selected)await selectBatch(state.selected,{quiet:true});else if(state.batches.length)await selectBatch(batchId(state.batches[0]),{quiet:true});else{renderSelected(null);renderDocuments(null);}if(!quiet)setNotice('已刷新。');}
  catch(error){if(!quiet)setNotice(`读取批次失败：${error.message}`,true);}
  finally{state.loading=false;}
}
async function downloadFile(path,filename){
  try{const response=await api(path);const blob=await response.blob();const url=URL.createObjectURL(blob);const link=element('a');link.href=url;link.download=filename;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);}
  catch(error){setNotice(`下载失败：${error.message}`,true);}
}
function reportActions(report){return report.actions || report.action_results || []}
function renderReport(report,doc){
  const target=$('#document-detail');target.replaceChildren();const id=documentId(doc),batch=state.selected;
  const summary=element('div','detail-summary');summary.append(badge(report.qualification_status || report.eligibility?.status || qualification(doc)),badge(report.delivery_status || delivery(doc)));
  if((report.delivery_status || delivery(doc))==='incomplete')summary.append(element('span','warning-copy','不完整，不能作为最终合同使用'));
  target.append(summary);
  const release=report.release_gate || report.ruleset_release;
  if(release && (release.auto_write===false || release.status==='closed')){
    target.append(element('p','warning-copy','规则自动写入尚未通过发布门槛；当前结果仅供评测。'));
  }
  if(report.error_code){const failure=element('div','detail-section');failure.append(element('h3','','处理失败原因'),element('p','warning-copy',report.error_code));for(const error of report.errors || [])failure.append(element('p','',`${error.stage || ''} · ${error.message || error.code || ''}`));target.append(failure);}
  const rawEvidence=report.qualification?.evidence || report.eligibility?.evidence || report.qualification_evidence || [];
  const evidence=Array.isArray(rawEvidence)?rawEvidence:[rawEvidence];
  if(evidence.length){const section=element('div','detail-section');section.append(element('h3','', '资格证据'));
    for(const item of evidence.slice(0,10)){const p=element('p','quote',item.quote || item.text || '');section.append(p);if(item.section_path)section.append(element('code','',`${item.section_path} · ${item.part_uri || ''} · ${item.paragraph_id || ''}`));}target.append(section);}
  const profile=report.profile || {};
  if(profile.classes?.length){const section=element('div','detail-section');section.append(element('h3','','份额收费画像'));for(const item of profile.classes){const value=v=>v===true?'收取':v===false?'不收取':'未确认';section.append(element('p','',`${item.name} 类 · 申购费：${value(item.subscription_fee)} · 销售服务费：${value(item.sales_service_fee)}`));for(const proof of item.evidence || [])section.append(element('p','quote',proof.quote));}if(!profile.fee_groups_verified)section.append(element('p','warning-copy','收费组证据尚未完整核验，依赖该画像的动作失败关闭。'));target.append(section);}
  const actions=reportActions(report);const actionSection=element('div','detail-section');actionSection.append(element('h3','',`规则动作 · ${actions.length}`));
  if(!actions.length)actionSection.append(element('p','', '无可展示的动作，详见 JSON 报告。'));
  for(const action of actions){const card=element('article','action-card'),head=element('header');head.append(element('strong','',action.action_id || action.id || '动作'),badge(action.status || action.action_status));card.append(head);
    const candidates=action.candidates || action.candidate_results || [];if(candidates.length)card.append(element('p','',`${candidates.length} 处候选；正文和内容摘要分别记录。`));
    if(action.failure_reason || action.error)card.append(element('p','warning-copy',action.failure_reason || action.error));
    if(action.auto_write===false)card.append(element('p','','自动写入关闭'));
    for(const candidate of candidates){const p=element('p','',`${label(candidate.status)} · ${candidate.region || candidate.location?.region || '区域未提供'} · ${candidate.section_path || candidate.location?.section_path || ''} · ${candidate.location || ''} [${candidate.char_start ?? ''},${candidate.char_end ?? ''})`);card.append(p);if(candidate.quote || candidate.original_text)card.append(element('p','quote',candidate.quote || candidate.original_text));if(candidate.reason)card.append(element('p','warning-copy',candidate.reason));}
    actionSection.append(card);
  }target.append(actionSection);
  const outputs=doc.downloads || {};const links=element('div','detail-section');links.append(element('h3','', '报告与产物'));const list=element('div','download-list');
  for(const [kindName,title,ext] of [['report_json','JSON 报告','json'],['report_md','Markdown 报告','md'],['redline','修订痕迹 DOCX','docx'],['final','最终版 DOCX','docx']]){
    if(['redline','final'].includes(kindName) && (report.delivery_status || delivery(doc))==='not_generated')continue;
    if(kindName==='final' && (report.delivery_status || delivery(doc))!=='complete')continue;
    if(!outputs[kindName])continue;
    const button=makeAction(title,()=>downloadFile(`/batches/${encodeURIComponent(batch)}/documents/${encodeURIComponent(id)}/download/${kindName}`,`${id}-${kindName}.${ext}`));list.append(button);
  }links.append(list);target.append(links);
}
async function showDocument(doc,{quiet=false}={}){
  const id=documentId(doc);try{const report=await json(`/batches/${encodeURIComponent(state.selected)}/documents/${encodeURIComponent(id)}/report`);state.detail=id;$('#detail-title').textContent=doc.filename || doc.original_filename || id;$('#detail-subtitle').textContent=`合同 ID ${id} · 规则 ${report.ruleset_version || state.batch?.ruleset_version || '—'}`;renderReport(report,doc);$('#detail-panel').hidden=false;if(!quiet)$('#detail-panel').scrollIntoView({behavior:'smooth',block:'start'});}
  catch(error){if(!quiet)setNotice(`读取合同报告失败：${error.message}`,true);}
}
async function createBatch(event){
  event.preventDefault();const files=[...$('#docx-files').files];if(!files.length)return setNotice('请选择 DOCX 文件。',true);
  if(files.some(file=>!file.name.toLowerCase().endsWith('.docx')))return setNotice('仅可提交 DOCX 文件。',true);
  const form=new FormData();form.append('ruleset_version',$('#ruleset-version').value.trim());for(const file of files)form.append('files',file);
  const button=$('#submit-batch');button.disabled=true;setNotice('正在创建批次…');
  try{const result=await json('/batches',{method:'POST',body:form});$('#upload-panel').hidden=true;$('#batch-form').reset();$('#ruleset-version').value='v1';$('#file-selection').textContent='尚未选择文件';setNotice(`批次 ${batchId(result)} 已创建。`);await refresh({quiet:true});await selectBatch(batchId(result),{quiet:true});}
  catch(error){setNotice(`创建批次失败：${error.message}`,true);}finally{button.disabled=false;}
}
function navigate(){const view=location.hash.replace('#','') || 'overview';const titles={overview:'批次总览',documents:'合同处理',delivery:'结果交付'};const title=titles[view] || titles.overview;$('#crumb-view').textContent=title;$('#page-title').textContent=title;for(const link of document.querySelectorAll('.nav-link'))link.classList.toggle('active',link.dataset.view===view);if(view==='documents')$('#documents-section').scrollIntoView({behavior:'smooth'});if(view==='delivery')$('#detail-panel').hidden?$('#documents-section').scrollIntoView({behavior:'smooth'}):$('#detail-panel').scrollIntoView({behavior:'smooth'});}
$('#new-batch-button').addEventListener('click',()=>{$('#upload-panel').hidden=false;$('#upload-panel').scrollIntoView({behavior:'smooth'});});
$('#close-upload').addEventListener('click',()=>$('#upload-panel').hidden=true);
$('#close-detail').addEventListener('click',()=>{$('#detail-panel').hidden=true;state.detail=null;});
$('#batch-form').addEventListener('submit',createBatch);
$('#docx-files').addEventListener('change',()=>{$('#file-selection').textContent=[...$('#docx-files').files].map(f=>f.name).join('、') || '尚未选择文件';});
$('#refresh-button').addEventListener('click',()=>refresh());
$('#dev-user').addEventListener('change',()=>{state.selected=null;state.detail=null;state.batch=null;state.batches=[];$('#detail-panel').hidden=true;$('#document-detail').replaceChildren();renderBatches();renderSelected(null);renderDocuments(null);refresh();});
window.addEventListener('hashchange',navigate);navigate();refresh();setInterval(()=>{if(state.selected && ['queued','running','leased','retry_wait'].includes(batchStatus(state.batch || {})))refresh({quiet:true});},5000);
