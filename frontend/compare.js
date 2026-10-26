(() => {
  'use strict';
  const api = window.FundLexWorkbench || {};
  const $ = id => document.getElementById(id);
  const esc = api.esc || (v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])));
  const state = { tasks: [], task: null, pairs: [], pairIndex: 0, selectedPairId: null, view: null, selection: null, selectionDraft: null, selectionDirty: false, selectionSaving: false, selectionToken: 0, selectionSaveToken: 0, poll: null, requestToken: 0, lineFrame: null, scrollFrame: null, scrollSource: null, identityToken: 0, listToken: 0, inputs: [{}], uploadDraft: null };
  const json = (path, options) => api.json ? api.json(path, options) : fetch(path, options).then(async r => { if (!r.ok) throw Error(await r.text()); return r.json(); });
  Object.assign(state, { diffIndex: 0, selectionBusy: false, generationKey: null });
  const text = id => ($(id) || {}).textContent || '';
  const fileName = file => String(file?.name || '').replace(/\\/g, '/').split('/').pop();
  const relativePath = file => {
    const raw=String(file?.webkitRelativePath || '').replace(/\\/g, '/');
    if(raw) return raw.split('/').filter(Boolean).slice(1).join('/') || fileName(file);
    return fileName(file);
  };
  function pairRow(pair = {}, index) {
    const selected = [pair.left?.name || fileName(pair._left), pair.right?.name || fileName(pair._right)].filter(Boolean).join(' / ');
    return `<div class="compare-pair-input" data-pair-index="${index}"><div class="compare-pair-head"><strong>第 ${index + 1} 组</strong><button type="button" class="btn-link" data-compare-remove="${index}" ${index ? '' : 'disabled'}>移除</button></div><div class="compare-side-inputs"><label><span>原版（基准）</span><input type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" data-compare-left="${index}"></label><label><span>对比版（修订）</span><input type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" data-compare-right="${index}"></label></div><p class="subnote compare-file-label" data-compare-label="${index}">${esc(selected||'尚未选择文件')}</p></div>`;
  }
  function renderInputs() { const box=$('compare-pair-inputs'); if (box) box.innerHTML = (state.inputs || [{}]).map(pairRow).join(''); }
  function syncInputIndexes() { document.querySelectorAll('#compare-pair-inputs .compare-pair-input').forEach((row,i)=>{ row.dataset.pairIndex=String(i); row.querySelector('[data-compare-left]')?.setAttribute('data-compare-left',String(i)); row.querySelector('[data-compare-right]')?.setAttribute('data-compare-right',String(i)); row.querySelector('[data-compare-remove]')?.setAttribute('data-compare-remove',String(i)); }); }
  function selectedFiles() { return (state.inputs || []).map(x => ({ left: x._left || x.left, right: x._right || x.right })).filter(x => x.left || x.right); }
  function resetFolders() { state.folderLeft=[]; state.folderRight=[]; for(const id of ['compare-left-folder','compare-right-folder'])if($(id))$(id).value=''; }
  function showCreate(show=true) { $('compare-create').hidden = !show; if (show) { clearTimeout(state.poll); state.requestToken++; $('compare-detail').hidden=true; $('compare-viewer').hidden=true; state.view=null; state.uploadDraft=null; state.inputs=[{}]; resetFolders(); $('compare-upload-message').textContent=''; $('compare-retry').hidden=true; $('compare-lines').replaceChildren(); renderInputs(); } }
  function statusLabel(v) { return ({pending:'待上传',queued:'排队中',leased:'处理中',running:'处理中',succeeded:'已完成',incomplete:'覆盖不完整',failed:'失败',retry_wait:'等待重试',sealed:'已提交',uploading:'上传中',completed:'已处理'}[v] || v || '—'); }
  function taskMetrics(task) {
    const pairs=task.pairs||[], counts=task.counts||{};
    const count=status=>pairs.length?pairs.filter(p=>p.status===status).length:(counts[status]||0);
    const failed=count('failed'), incomplete=count('incomplete');
    const pending=pairs.length?pairs.filter(p=>!['succeeded','incomplete','failed'].includes(p.status)).length:(counts.pending||0);
    const results=pairs.filter(p=>['succeeded','incomplete'].includes(p.status)&&Number.isInteger(p.summary?.total));
    const notes=[pending?`${pending} 组待处理`:'',failed?`${failed} 组失败`:'',incomplete?`${incomplete} 组覆盖不完整`:''].filter(Boolean);
    const total=results.reduce((sum,p)=>sum+p.summary.total,0);
    const differences=[results.length?`${notes.length?'已检出 ':''}${total} 处`:pending?'待处理':'无可用结果',...notes].join(' · ');
    const status=task.status==='completed'?(failed||incomplete?`已处理 · ${notes.join(' · ')}`:count('succeeded')? '已完成':'已处理'):statusLabel(task.status);
    return {status,differences};
  }
  function renderTasks() {
    const box=$('compare-task-list'); if (!box) return;
    if (!state.tasks.length) { box.innerHTML='<div class="empty"><strong>还没有合同对比任务</strong><p>创建一组或多组左右合同开始比较。</p></div>'; return; }
    box.innerHTML=`<div class="table-wrap"><table class="table"><thead><tr><th>任务</th><th>合同组</th><th>状态</th><th>差异</th><th></th></tr></thead><tbody>${state.tasks.map(t=>{const m=taskMetrics(t);return `<tr><td>${esc(t.name)}</td><td>${t.total||0}</td><td>${esc(m.status)}</td><td>${esc(m.differences)}</td><td><button type="button" class="btn btn-sm" data-compare-task="${esc(t.id)}">查看</button></td></tr>`;}).join('')}</tbody></table></div>`;
  }
  async function loadTasks() { const token=++state.listToken,identity=state.identityToken; try { const p=await json('/api/compare/tasks'); if(token!==state.listToken||identity!==state.identityToken)return; state.tasks=p.items||[]; renderTasks(); } catch (e) { if(token===state.listToken&&identity===state.identityToken)$('compare-task-list').innerHTML=`<p class="field-error">读取对比任务失败：${esc(e.message)}</p>`; } }
  function renderTask(task) {
    state.task=task; state.pairs=task.pairs||[]; $('compare-detail').hidden=false; $('compare-task-name').textContent=task.name||'合同对比'; $('compare-task-status').textContent=`${taskMetrics(task).status} · ${state.pairs.length} 组`;
    state.tasks=state.tasks.map(t=>t.id===task.id?task:t); renderTasks(); renderPairs();
  }
  function renderPairs() {
    $('compare-pair-list').innerHTML=`<div class="compare-pair-statuses">${state.pairs.map((p,i)=>`<button type="button" class="compare-pair-status ${p.id===state.selectedPairId?'is-selected':''} ${['succeeded','incomplete'].includes(p.status)?'is-done':''} ${p.status==='incomplete'?'is-incomplete':''} ${p.status==='failed'||p.viewError?'is-failed':''}" data-compare-pair="${i}"><span class="compare-pair-number">${String(i+1).padStart(2,'0')}</span><span class="compare-pair-main"><strong>${esc(p.label||`第 ${i+1} 组`)}</strong><small>${esc(p.left?.name||'原版未命名')} → ${esc(p.right?.name||'对比版未命名')}</small></span><span class="compare-pair-state">${esc(statusLabel(p.status))}${p.summary?` · ${p.summary.total} 处`:''}</span>${p.error_code||p.viewError?`<span class="compare-pair-error" role="status">${esc(p.viewError||`处理失败：${p.error_code}`)}</span>`:''}</button>`).join('')}</div>`;
  }
  function markFiles(form, files, pair) { const ids=[]; for (const side of ['left','right']) { form.append('files',files[side],pair[side].name); ids.push(pair[side].client_id); } form.append('client_ids', JSON.stringify(ids)); }
  async function continueUploads() {
    const draft=state.uploadDraft, message=$('compare-upload-message'); if(!draft)return;
    const identity=state.identityToken; $('compare-submit').disabled=true; $('compare-retry').hidden=true;
    try {
      for (let i=draft.next;i<draft.files.length;i++) {
        const x=draft.files[i]; message.textContent=`正在上传第 ${i+1} / ${draft.files.length} 组…`;
        const form=new FormData(); markFiles(form,x,draft.pairs[i]); const uploaded=await json(`/api/compare/tasks/${encodeURIComponent(draft.task.id)}/uploads`,{method:'POST',body:form});
        if(identity!==state.identityToken)return; const receipts=uploaded.receipts||[],bad=['left','right'].map(side=>receipts.find(r=>r.client_id===draft.pairs[i][side].client_id)).filter(r=>!r||!['accepted','already_accepted'].includes(r.status));
        if(bad.length)throw Error(`第 ${i+1} 组上传未完成：${bad.map(r=>r?`${r.client_id}（${r.error_code||r.status}）`:'缺少上传回执').join('、')}`);
        draft.next=i+1;
      }
      message.textContent='文件已上传，正在提交对比任务…'; await json(`/api/compare/tasks/${encodeURIComponent(draft.task.id)}/seal`,{method:'POST'}); if(identity!==state.identityToken)return;
      message.textContent='已提交，对比任务正在处理。'; state.uploadDraft=null; showCreate(false); await loadTasks(); await openTask(draft.task.id);
    } catch(e) { if(identity===state.identityToken){message.textContent=`上传中断：${e.message}。已完成的文件已保留，可点击“继续上传”。`; $('compare-retry').hidden=false;} }
    finally { if(identity===state.identityToken)$('compare-submit').disabled=false; }
  }
  async function createTask() {
    const files=selectedFiles(), message=$('compare-upload-message');
    if (!files.length || files.some(x=>!x.left||!x.right)) { message.textContent='每组都需要同时选择原版和对比版 DOCX。'; return; }
    const identity=state.identityToken; const name=($('compare-name').value||'合同对比').trim(); const pairs=files.map((x,i)=>{const leftId=`L${i}-${crypto.randomUUID()}`,rightId=`R${i}-${crypto.randomUUID()}`;return {client_pair_id:`P${i+1}`,label:`合同 ${i+1}`,left:{client_id:leftId,name:fileName(x.left),size:x.left.size},right:{client_id:rightId,name:fileName(x.right),size:x.right.size}};});
    const key=`compare-${Date.now()}-${crypto.randomUUID()}`; message.textContent='正在创建对比任务…'; $('compare-submit').disabled=true;
    try { const task=await json('/api/compare/tasks',{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':key},body:JSON.stringify({name,pairs})}); if(identity!==state.identityToken)return; state.uploadDraft={task,pairs,files,next:0}; await continueUploads(); }
    catch(e) { if(identity===state.identityToken){message.textContent=`创建任务失败：${e.message}`;$('compare-submit').disabled=false;} }
  }
  function blockFor(side, id) { return document.querySelector(`#compare-${side}-pane [data-block-id="${CSS.escape(id)}"]`); }
  function targetFor(side, span, item) { const pane=$(`compare-${side}-pane`); if(!pane)return null; const id=span?.block_id || item?.[`${side}_anchor`]?.block_id; return id ? blockFor(side,id) : pane.querySelector('.compare-block'); }
  function drawLines() {
    if(state.lineFrame!==null)return;
    state.lineFrame=requestAnimationFrame(()=>{
      state.lineFrame=null;
      const cols=$('compare-columns'),svg=$('compare-lines'); if(!cols||!svg)return;
      svg.replaceChildren(); if(!state.view||$('compare-viewer').hidden)return;
      const cr=cols.getBoundingClientRect(),left=$('compare-left-pane'),right=$('compare-right-pane'),lr=left.getBoundingClientRect(),rr=right.getBoundingClientRect();
      if(!cr.width||!cr.height)return;
      svg.setAttribute('viewBox',`0 0 ${cr.width} ${cr.height}`);
       const active=visibleDiffs()[state.diffIndex]?.id,activeOnly=$('compare-active-only')?.checked,fragment=document.createDocumentFragment();
      const visible=(rect,pane)=>rect.bottom>=pane.top&&rect.top<=pane.bottom&&rect.right>=pane.left&&rect.left<=pane.right;
      const leftMarks=new Map([...left.querySelectorAll('[data-diff-id]')].map(n=>[n.dataset.diffId,n])),rightMarks=new Map([...right.querySelectorAll('[data-diff-id]')].map(n=>[n.dataset.diffId,n]));
      for(const d of state.view.diffs||[]) {
        if(activeOnly&&d.id!==active)continue;
        const l=leftMarks.get(d.id),r=rightMarks.get(d.id); if(!l||!r)continue;
        const a=l.getBoundingClientRect(),b=r.getBoundingClientRect();
        if(d.id!==active&&!visible(a,lr)&&!visible(b,rr))continue;
        const x1=a.right-cr.left,y1=a.top+a.height/2-cr.top,x2=b.left-cr.left,y2=b.top+b.height/2-cr.top,path=document.createElementNS('http://www.w3.org/2000/svg','path');
        path.setAttribute('d',`M ${x1} ${y1} C ${(x1+x2)/2} ${y1}, ${(x1+x2)/2} ${y2}, ${x2} ${y2}`); path.dataset.diffId=d.id; path.classList.toggle('active',d.id===active); fragment.append(path);
      }
      svg.append(fragment);
    });
  }
  function syncPaneScroll(source) {
    if (window.matchMedia('(max-width: 760px)').matches) { drawLines(); return; }
    if (state.scrollSource && state.scrollSource !== source) { drawLines(); return; }
    const panes = [$('compare-left-pane'), $('compare-right-pane')].filter(Boolean), target = panes.find(p => p !== source);
    if (!target) return;
    state.scrollSource = source;
    cancelAnimationFrame(state.scrollFrame);
    state.scrollFrame = requestAnimationFrame(() => {
      const sourceMax = Math.max(0, source.scrollHeight - source.clientHeight), targetMax = Math.max(0, target.scrollHeight - target.clientHeight);
      target.scrollTop = (sourceMax ? source.scrollTop / sourceMax : 0) * targetMax;
      drawLines();
      state.scrollFrame = requestAnimationFrame(() => { state.scrollSource = null; state.scrollFrame = null; drawLines(); });
    });
  }
  function selectionDecision(id) { return state.selectionDraft?.[id] || state.selection?.selection?.decisions?.[id] || 'pending'; }
  function selectionBinding() { const s=state.selection; if(!s?.selection)return null; return {expected_epoch:s.selection.selection_epoch,result_sha256:s.result_sha256,left_source_sha256:s.left_source_sha256,right_source_sha256:s.right_source_sha256}; }
  function selectionStatus(message, error=false) { const node=$('compare-selection-status'); if(node){node.textContent=message||'';node.classList.toggle('is-error',!!error);} }
  function selectionCounts() { const ds=state.view?.diffs||[], counts={pending:0,left:0,right:0}; ds.forEach(d=>{const value=selectionDecision(d.id);if(counts[value]!==undefined)counts[value]++;}); return {counts,total:ds.length,pending:counts.pending}; }
  function selectionIssues() {
    const issues=[...(state.selection?.assessment?.issues||[])];
    if((state.view?.diffs||[]).some(d=>d.type!=='modify'))issues.push({detail:'当前版本暂不支持新增或删除整段内容，请人工处理这些差异。',blocking:true});
    return issues;
  }
  function selectionCanGenerate() { return !!state.selection&&!state.selectionDirty&&!state.selectionSaving&&!state.selectionBusy&&!selectionCounts().pending&&!selectionIssues().some(x=>x.blocking); }
  function selectionContext() { return {pairId:state.selectedPairId,token:state.selectionToken,identity:state.identityToken}; }
  function selectionCurrent(context) { return context.pairId===state.selectedPairId&&context.token===state.selectionToken&&context.identity===state.identityToken; }
  function resetSelection() {
    state.selectionToken++;state.selectionSaveToken++;state.selection=null;state.selectionDraft=null;
    state.selectionDirty=false;state.selectionSaving=false;state.selectionBusy=false;state.generationKey=null;
    selectionStatus('');$('compare-selection-downloads')?.replaceChildren();renderSelection();
  }
  function renderSelectionDownloads() {
    const box=$('compare-selection-downloads'); if(!box)return;
    const artifacts=state.selectionDirty?[]:(state.selection?.artifacts||[]).filter(x=>x.status==='current');
    if(!artifacts.length){box.replaceChildren();return;}
    const labels={selected_final:'下载选择版 DOCX',selected_redline:'下载选择修订版 DOCX',selection_report_markdown:'下载选择报告（Markdown）',selection_report_json:'下载选择报告（JSON）'};
    box.innerHTML=artifacts.map(item=>`<div class="compare-artifact"><button class="btn btn-sm" type="button" data-selection-download="${esc(item.download_url)}" data-selection-filename="${esc(`compare-v${item.version}-${item.kind}`)}">${esc(labels[item.kind]||item.kind)} · v${item.version}</button><small>SHA-256：${esc(item.sha256)}</small></div>`).join('');
  }
  function renderSelection() {
    const s=state.selection, node=$('compare-selection-progress'), buttons=document.querySelectorAll('#compare-selection-left-all,#compare-selection-right-all,#compare-selection-preview,#compare-selection-generate,#compare-selection-save,#compare-selection-pending');
    if(!s){if(node)node.textContent='正在读取选择状态…';buttons.forEach(x=>{x.disabled=true;});return;}
    const {counts,total,pending}=selectionCounts();
    if(node)node.textContent=`已选择 ${total-pending} / ${total} 处 · 待选择 ${pending}`;
    const ready=selectionCanGenerate();
    const blocked=selectionIssues().some(x=>x.blocking), busy=state.selectionSaving||state.selectionBusy;
    $('compare-selection-issues').textContent=selectionIssues().filter(x=>x.blocking).map(x=>x.detail||x.code).join(' ');
    const preview=$('compare-selection-preview'), generate=$('compare-selection-generate');
    if(preview)preview.disabled=busy||state.selectionDirty;
    if(generate){generate.disabled=!ready;generate.title=pending?'所有差异都需要明确选择左侧或右侧':blocked?'当前结果包含暂不支持的结构':'生成选择版';}
    buttons.forEach(x=>{if(x!==preview&&x!==generate)x.disabled=busy;});
    $('compare-selection-save').disabled=busy||!state.selectionDirty;
    $('compare-selection-pending').disabled=busy||!pending;
    for(const side of ['left','right'])$(`compare-selection-${side}-all`).textContent=`全部采用${side==='left'?'左':'右'}侧（${total}处）`;
    renderSelectionDownloads();
  }
  async function loadSelection(pairId) {
    resetSelection();const token=state.selectionToken;
    try { const payload=await json(`/api/compare/pairs/${encodeURIComponent(pairId)}/selection`); if(token!==state.selectionToken||pairId!==state.selectedPairId)return; state.selection=payload;state.selectionDraft={...(payload.selection?.decisions||{})};renderSelection();renderDiffList(); }
    catch(e){if(token===state.selectionToken){selectionStatus(`读取选择状态失败：${e.message}`,true);renderSelection();}}
  }
  async function saveSelectionDraft() {
    const binding=selectionBinding(); if(!binding||!state.selectionDraft)return;
    if(state.selectionSaving||state.selectionBusy)return;
    const context=selectionContext(), token=++state.selectionSaveToken, decisions={...state.selectionDraft};
    state.selectionSaving=true;state.selectionDirty=true;selectionStatus('正在保存选择…');renderSelection();renderDiffList();
    try {
      const payload=await json(`/api/compare/pairs/${encodeURIComponent(context.pairId)}/selection`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({...binding,decisions})});
      if(!selectionCurrent(context)||token!==state.selectionSaveToken)return;
      state.selection=payload;state.selectionDraft={...payload.selection.decisions};state.selectionDirty=false;state.generationKey=null;selectionStatus('已保存');
    } catch(e) {
      if(!selectionCurrent(context)||token!==state.selectionSaveToken)return;
      if(e.raw==='SELECTION_EPOCH_CONFLICT') {
        try {
          const latest=await json(`/api/compare/pairs/${encodeURIComponent(context.pairId)}/selection`);
          if(!selectionCurrent(context)||token!==state.selectionSaveToken)return;
          if(['result_sha256','left_source_sha256','right_source_sha256'].every(k=>latest[k]===state.selection[k]))state.selection=latest;
        } catch { /* Keep the local map; a failed reload must not discard it. */ }
      }
      if(selectionCurrent(context)){state.selectionDirty=true;selectionStatus('保存未完成，本地选择已保留。请核对后点击“保存当前选择”重试。',true);}
    } finally {if(selectionCurrent(context)&&token===state.selectionSaveToken){state.selectionSaving=false;renderSelection();renderDiffList();}}
  }
  function chooseSelection(id, choice) { if(!state.selection||state.selectionSaving||state.selectionBusy)return; state.selectionDraft={...(state.selectionDraft||{}),[id]:choice};state.selectionDirty=true;saveSelectionDraft(); }
  function setAllSelections(choice) { if(!state.selection||state.selectionSaving||state.selectionBusy)return; const next={};(state.view?.diffs||[]).forEach(item=>{next[item.id]=choice;});state.selectionDraft=next;state.selectionDirty=true;saveSelectionDraft(); }
  async function selectionAction(kind) {
    const binding=selectionBinding();if(!binding||state.selectionSaving||state.selectionBusy||state.selectionDirty||(kind==='generate'&&!selectionCanGenerate()))return;
    const context=selectionContext();state.selectionBusy=true;
    selectionStatus(kind==='generate'?'正在生成选择版 DOCX，请稍候…':'正在检查生成条件…');renderSelection();renderDiffList();
    const headers={'Content-Type':'application/json'};
    if(kind==='generate'){state.generationKey ||= `compare-${crypto.randomUUID()}`;headers['Idempotency-Key']=state.generationKey;}
    try {
      const result=await json(`/api/compare/pairs/${encodeURIComponent(context.pairId)}/selection/${kind}`,{method:'POST',headers,body:JSON.stringify(binding)});
      if(!selectionCurrent(context))return;
      if(kind==='generate'){state.selection={...state.selection,artifacts:result.artifacts||[]};selectionStatus(`已生成 v${result.version}，可下载选择版、修订版和报告。`);}
      else {state.selection.assessment=result.assessment;const pending=result.assessment.pending_ids.length,blocked=selectionIssues().some(x=>x.blocking);selectionStatus(pending?`仍有 ${pending} 处待选择，全部明确选择后才能生成。`:blocked?'当前结构暂不支持生成，请查看说明。':'当前选择可以提交生成；生成时还会校验 DOCX 结构。',!!(pending||blocked));}
    } catch(e){if(selectionCurrent(context))selectionStatus(e.raw||e.message,true);}
    finally {if(selectionCurrent(context)){state.selectionBusy=false;renderSelection();renderDiffList();}}
  }
  const previewSelection=()=>selectionAction('preview'), generateSelection=()=>selectionAction('generate');
  async function downloadSelection(url, filename) {
    const context=selectionContext();
    try {
      const headers={};const authToken=sessionStorage.getItem('fundlex-auth-token'),identity=$('dev-user')?.value?.trim();
      if(authToken)headers.Authorization=`Bearer ${authToken}`;if(identity)headers['X-FundLex-User']=identity;
      const response=await window.fetch((api.appPath?api.appPath(url):url),{headers,cache:'no-store'});
      if(!response.ok)throw Error(`下载失败（${response.status}）`);
      const blob=await response.blob();
      if(!selectionCurrent(context))return;
      const disposition=response.headers.get('Content-Disposition')||'',encoded=disposition.match(/filename\*=UTF-8''([^;]+)/i),plain=disposition.match(/filename="([^"]+)"/i);
      if(encoded){try{filename=decodeURIComponent(encoded[1]);}catch{}}else if(plain)filename=plain[1];
      const object=URL.createObjectURL(blob),a=document.createElement('a');a.href=object;a.download=filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(object),1000);selectionStatus('下载已开始。');
    } catch(e){if(selectionCurrent(context))selectionStatus(e.message,true);}
  }
  function visibleDiffs() { const all=state.view?.diffs||[], filter=$('compare-diff-filter')?.value||''; return filter?all.filter(x=>x.type===filter):all; }
  function focusDiff(index) { const ds=visibleDiffs(); if(!ds.length){ $('compare-diff-counter').textContent='0 / 0'; return; } state.diffIndex=(index+ds.length)%ds.length; const id=ds[state.diffIndex].id; document.querySelectorAll('.compare-diff.is-active,.compare-diff-item.is-active').forEach(n=>n.classList.remove('is-active')); document.querySelectorAll(`[data-diff-id="${CSS.escape(id)}"]`).forEach(n=>n.classList.add('is-active')); document.querySelector(`[data-compare-diff="${CSS.escape(id)}"]`)?.classList.add('is-active'); $('compare-diff-counter').textContent=`${state.diffIndex+1} / ${ds.length}`; for(const side of ['left','right']) { const pane=$(`compare-${side}-pane`), target=pane?.querySelector(`[data-diff-id="${CSS.escape(id)}"]`); if(pane&&target){const pr=pane.getBoundingClientRect(),tr=target.getBoundingClientRect(); pane.scrollTo({top:pane.scrollTop+(tr.top+tr.height/2)-(pr.top+pr.height/2),behavior:'smooth'});}} requestAnimationFrame(drawLines); }
  function renderDiffList() { const d=visibleDiffs(), disabled=!state.selection||state.selectionSaving; $('compare-diff-list').innerHTML=d.length?d.map((x,i)=>{const choice=selectionDecision(x.id);return `<div class="compare-diff-item ${choice!=='pending'?'is-selected-choice':''}" data-compare-diff="${esc(x.id)}"><button type="button" class="compare-diff-jump" data-compare-diff="${esc(x.id)}"><span>${i+1}</span><strong>${esc(x.type==='modify'?'修改':x.type==='insert'?'新增':'删除')}</strong><span>${esc(x.section||'正文')} · ${esc(x.left?.text||'')} ${x.right?.text?'→ '+esc(x.right.text):''}</span></button><div class="compare-choice" role="group" aria-label="${esc(x.id)} 采用哪一侧"><label class="${choice==='left'?'is-checked':''}"><input type="radio" name="choice-${esc(x.id)}" value="left" data-selection-choice="left" data-diff-id="${esc(x.id)}" ${choice==='left'?'checked':''} ${disabled?'disabled':''}>采用左侧</label><label class="${choice==='right'?'is-checked':''}"><input type="radio" name="choice-${esc(x.id)}" value="right" data-selection-choice="right" data-diff-id="${esc(x.id)}" ${choice==='right'?'checked':''} ${disabled?'disabled':''}>采用右侧</label></div></div>`;}).join(''):'<p class="empty">当前筛选条件下没有差异。</p>'; }
  function renderViewer(payload) {
    state.view=payload; state.diffIndex=0; const d=payload.diffs||[]; $('compare-viewer').hidden=false; $('compare-pair-title').textContent=payload.pair?.label||'合同对比'; $('compare-left-name').textContent=payload.left?.name||'原版合同'; $('compare-right-name').textContent=payload.right?.name||'对比版合同'; const s=payload.summary||{}; $('compare-summary').textContent=`共 ${s.total||0} 处差异 · 修改 ${s.modify||0} · 新增 ${s.insert||0} · 删除 ${s.delete||0}`; const cov=payload.coverage||{}; const incomplete=cov.status!=='complete'; $('compare-coverage').hidden=!incomplete; $('compare-coverage').className=incomplete?'is-incomplete':''; $('compare-coverage').textContent=incomplete?`覆盖不完整：以下内容未纳入比较。请人工复核，不要据此确认全文无差异。${(cov.warnings||[]).length?' 未覆盖：'+cov.warnings.join('、'):''}`:'覆盖完整'; $('compare-left-pane').innerHTML=payload.left.html||''; $('compare-right-pane').innerHTML=payload.right.html||''; document.querySelectorAll('#compare-left-pane [data-diff-id],#compare-right-pane [data-diff-id]').forEach(mark=>{mark.tabIndex=0;mark.setAttribute('role','button');mark.setAttribute('aria-label','定位此处差异');}); $('compare-diff-counter').textContent='0 / 0'; renderDiffList(); if(!d.length)$('compare-diff-list').innerHTML=`<p class="empty">${incomplete?'已覆盖范围内没有发现文字差异，无法确认全文无差异。':'两份合同没有文字差异。'}</p>`; drawLines();if(d.length)focusDiff(0); }
  async function openPair(index) {
    const p=state.pairs[index];if(!p)return;
    if(state.selectionDirty){selectionStatus('请先保存当前选择，再切换合同组。',true);return;}
    resetSelection();const token=++state.requestToken;
    state.pairIndex=index;state.selectedPairId=p.id;state.view=null;renderPairs();
    $('compare-viewer').hidden=true;$('compare-lines').replaceChildren();$('compare-pair-counter').textContent=`${index+1} / ${state.pairs.length}`;
    if(!['succeeded','incomplete'].includes(p.status))return;
    try {const payload=await json(`/api/compare/pairs/${encodeURIComponent(p.id)}/view`);if(token===state.requestToken){p.viewError='';renderPairs();renderViewer(payload);await loadSelection(p.id);}}
    catch(e){if(token===state.requestToken){p.viewError=`读取结果失败：${e.message}`;renderPairs();}}
  }
   async function openTask(id) { clearTimeout(state.poll); const token=++state.requestToken; try { const task=await json(`/api/compare/tasks/${encodeURIComponent(id)}`); if(token!==state.requestToken)return; const previousPairId=state.selectedPairId; renderTask(task); const kept=state.pairs.findIndex(p=>p.id===previousPairId); const idx=kept>=0?kept:state.pairs.findIndex(p=>['succeeded','incomplete'].includes(p.status)); if(idx>=0){ if(previousPairId===state.pairs[idx]?.id&&state.view) { $('compare-pair-counter').textContent=`${idx+1} / ${state.pairs.length}`; } else await openPair(idx); } else $('compare-viewer').hidden=true; if (['queued','running','uploading'].includes(state.task?.status)) { state.poll=setTimeout(()=>openTask(id),2500); } } catch(e) { if(token===state.requestToken)$('compare-task-status').textContent=`读取任务失败：${e.message}`; } }
  function bind() {
    document.addEventListener('fundlex:identity-reset',resetSelection);
    window.addEventListener('beforeunload',event=>{if(state.selectionDirty){event.preventDefault();event.returnValue='';}});
    $('compare-new')?.addEventListener('click',()=>showCreate(true)); $('compare-add-pair')?.addEventListener('click',()=>{const index=state.inputs.length;state.inputs.push({});$('compare-pair-inputs')?.insertAdjacentHTML('beforeend',pairRow({},index));syncInputIndexes();}); $('compare-submit')?.addEventListener('click',createTask); $('compare-refresh')?.addEventListener('click',loadTasks);
    $('compare-prev-diff')?.addEventListener('click',()=>focusDiff(state.diffIndex-1)); $('compare-next-diff')?.addEventListener('click',()=>focusDiff(state.diffIndex+1)); $('compare-prev-pair')?.addEventListener('click',()=>openPair(Math.max(0,state.pairIndex-1))); $('compare-next-pair')?.addEventListener('click',()=>openPair(Math.min(state.pairs.length-1,state.pairIndex+1))); $('compare-report')?.addEventListener('click',()=>{if(!state.view)return;const blob=new Blob([JSON.stringify(state.view,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`${state.task?.name||'合同对比'}-差异报告.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}); $('compare-selection-left-all')?.addEventListener('click',()=>setAllSelections('left')); $('compare-selection-right-all')?.addEventListener('click',()=>setAllSelections('right')); $('compare-selection-pending')?.addEventListener('click',()=>{const index=visibleDiffs().findIndex(item=>selectionDecision(item.id)==='pending');if(index>=0)focusDiff(index);}); $('compare-selection-save')?.addEventListener('click',saveSelectionDraft); $('compare-selection-preview')?.addEventListener('click',previewSelection); $('compare-selection-generate')?.addEventListener('click',generateSelection); $('compare-active-only')?.addEventListener('change',drawLines); $('compare-diff-filter')?.addEventListener('change',()=>{state.diffIndex=0;renderDiffList();focusDiff(0);}); $('compare-retry')?.addEventListener('click',continueUploads); document.querySelectorAll('[data-compare-side]').forEach(btn=>btn.addEventListener('click',()=>{document.querySelectorAll('[data-compare-side]').forEach(x=>x.classList.toggle('is-active',x===btn));$('compare-viewer').dataset.mobileSide=btn.dataset.compareSide;}));
      document.addEventListener('click',e=>{ const task=e.target.closest('[data-compare-task]');if(task){openTask(task.dataset.compareTask);return;}const pair=e.target.closest('[data-compare-pair]');if(pair){openPair(Number(pair.dataset.comparePair));return;}const download=e.target.closest('[data-selection-download]');if(download){downloadSelection(download.dataset.selectionDownload,download.dataset.selectionFilename);return;}const diff=e.target.closest('[data-compare-diff]');if(diff&&!e.target.closest('input')){focusDiff(visibleDiffs().findIndex(x=>x.id===diff.dataset.compareDiff));return;}const mark=e.target.closest('#compare-left-pane [data-diff-id],#compare-right-pane [data-diff-id]');if(mark){focusDiff(visibleDiffs().findIndex(x=>x.id===mark.dataset.diffId));return;}const remove=e.target.closest('[data-compare-remove]');if(remove){const index=Number(remove.dataset.compareRemove),row=remove.closest('.compare-pair-input');state.inputs.splice(index,1);row?.remove();if(!state.inputs.length){state.inputs=[{}];renderInputs();}else syncInputIndexes();return;} });
     document.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.matches('#compare-left-pane [data-diff-id],#compare-right-pane [data-diff-id]')){e.preventDefault();focusDiff(visibleDiffs().findIndex(x=>x.id===e.target.dataset.diffId));}});
      document.addEventListener('change',e=>{const choice=e.target.closest('[data-selection-choice]');if(choice){chooseSelection(choice.dataset.diffId,choice.value);return;}const row=e.target.closest('.compare-pair-input');if(row&&e.target.matches('input[type=file]')){const i=Number(row.dataset.pairIndex),entry=state.inputs[i]||(state.inputs[i]={});entry[e.target.matches('[data-compare-left]')?'_left':'_right']=e.target.files?.[0]||null;row.querySelector('.compare-file-label').textContent=[entry._left?.name,entry._right?.name].filter(Boolean).join(' / ')||'尚未选择文件';return;}if(e.target.id==='compare-left-folder'||e.target.id==='compare-right-folder'){const side=e.target.id.includes('left')?'left':'right';state[`folder${side[0].toUpperCase()+side.slice(1)}`]=[...e.target.files].filter(f=>fileName(f).toLowerCase().endsWith('.docx')).sort((a,b)=>relativePath(a).localeCompare(relativePath(b)));const other=side==='left'?state.folderRight:state.folderLeft;if(!other?.length)return;const left=state.folderLeft||[],right=state.folderRight||[],map=new Map(right.map(f=>[relativePath(f),f])),used=new Set(),entries=left.map(f=>{const r=map.get(relativePath(f));if(r)used.add(r);return {_left:f,_right:r||null};});for(const f of right)if(!used.has(f))entries.push({_left:null,_right:f});state.inputs=entries;renderInputs();$('compare-upload-message').textContent=`已按相对路径配对 ${entries.filter(x=>x._left&&x._right).length} 组；${entries.filter(x=>!x._left||!x._right).length} 个文件未配对，可手工补齐。`;}});
     const cols=$('compare-columns'); if(cols){ for(const pane of [$('compare-left-pane'),$('compare-right-pane')])pane?.addEventListener('scroll',()=>syncPaneScroll(pane),{passive:true}); window.addEventListener('resize',drawLines); if(window.ResizeObserver)new ResizeObserver(drawLines).observe(cols); }
      document.addEventListener('fundlex:view',e=>{if(e.detail==='compare'){loadTasks();drawLines();}}); document.addEventListener('fundlex:identity-reset',()=>{clearTimeout(state.poll);state.identityToken++;state.listToken++;state.tasks=[];state.task=null;state.pairs=[];state.selectedPairId=null;state.view=null;state.selection=null;state.selectionDraft=null;state.selectionDirty=false;state.uploadDraft=null;state.inputs=[{}];state.requestToken++;state.selectionToken++;resetFolders();$('compare-create').hidden=true;$('compare-submit').disabled=false;$('compare-retry').hidden=true;$('compare-upload-message').textContent='';$('compare-name').value='';$('compare-detail').hidden=true;$('compare-viewer').hidden=true;$('compare-left-pane').innerHTML='';$('compare-right-pane').innerHTML='';$('compare-diff-list').innerHTML='';$('compare-selection-downloads').replaceChildren();selectionStatus('');$('compare-lines').replaceChildren();$('compare-diff-counter').textContent='0 / 0';renderInputs();renderTasks();}); state.inputs=[{}];renderInputs(); loadTasks();
  }
  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded',bind); else bind();
})();
