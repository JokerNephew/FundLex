(() => {
  'use strict';
  const api = window.FundLexWorkbench || {};
  const $ = id => document.getElementById(id);
  const esc = api.esc || (v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])));
  const state = { tasks: [], task: null, pairs: [], pairIndex: 0, view: null, diffIndex: 0, poll: null, requestToken: 0, lineFrame: null, identityToken: 0, listToken: 0 };
  const json = (path, options) => api.json ? api.json(path, options) : fetch(path, options).then(async r => { if (!r.ok) throw Error(await r.text()); return r.json(); });
  const text = id => ($(id) || {}).textContent || '';
  const fileName = file => String(file?.name || '').replace(/\\/g, '/').split('/').pop();
  const relativePath = file => {
    const raw=String(file?.webkitRelativePath || '').replace(/\\/g, '/');
    if(raw) return raw.split('/').filter(Boolean).slice(1).join('/') || fileName(file);
    return fileName(file);
  };
  function pairRow(pair = {}, index) {
    const selected = [pair.left?.name || fileName(pair._left), pair.right?.name || fileName(pair._right)].filter(Boolean).join(' / ');
    return `<div class="compare-pair-input" data-pair-index="${index}"><div class="compare-pair-head"><strong>第 ${index + 1} 组</strong><button type="button" class="btn-link" data-compare-remove="${index}" ${index ? '' : 'disabled'}>移除</button></div><label>左侧合同<input type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" data-compare-left="${index}"></label><label>右侧合同<input type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" data-compare-right="${index}"></label><p class="subnote compare-file-label" data-compare-label="${index}">${esc(selected||'尚未选择文件')}</p></div>`;
  }
  function renderInputs() { const box=$('compare-pair-inputs'); if (box) box.innerHTML = (state.inputs || [{}]).map(pairRow).join(''); }
  function syncInputIndexes() { document.querySelectorAll('#compare-pair-inputs .compare-pair-input').forEach((row,i)=>{ row.dataset.pairIndex=String(i); row.querySelector('[data-compare-left]')?.setAttribute('data-compare-left',String(i)); row.querySelector('[data-compare-right]')?.setAttribute('data-compare-right',String(i)); row.querySelector('[data-compare-remove]')?.setAttribute('data-compare-remove',String(i)); }); }
  function selectedFiles() { return (state.inputs || []).map(x => ({ left: x._left || x.left, right: x._right || x.right })).filter(x => x.left || x.right); }
  function resetFolders() { state.folderLeft=[]; state.folderRight=[]; for(const id of ['compare-left-folder','compare-right-folder'])if($(id))$(id).value=''; }
  function showCreate(show=true) { $('compare-create').hidden = !show; if (show) { clearTimeout(state.poll); state.requestToken++; $('compare-detail').hidden=true; $('compare-viewer').hidden=true; state.view=null; state.inputs=[{}]; resetFolders(); $('compare-upload-message').textContent=''; $('compare-lines').replaceChildren(); renderInputs(); } }
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
    $('compare-pair-list').innerHTML=`<div class="compare-pair-statuses">${state.pairs.map((p,i)=>`<button type="button" class="compare-pair-status ${['succeeded','incomplete'].includes(p.status)?'is-done':''} ${p.status==='incomplete'?'is-incomplete':''} ${p.status==='failed'||p.viewError?'is-failed':''}" data-compare-pair="${i}"><strong>第 ${i+1} 组</strong><span>${esc(p.label||'')}</span><small>${esc(statusLabel(p.status))}${p.summary?` · ${p.summary.total} 处`:''}</small>${p.error_code||p.viewError?`<span class="compare-pair-error" role="status">${esc(p.viewError||`处理失败：${p.error_code}`)}</span>`:''}</button>`).join('')}</div>`;
  }
  function markFiles(form, files, pair) { const ids=[]; for (const side of ['left','right']) { form.append('files',files[side],pair[side].name); ids.push(pair[side].client_id); } form.append('client_ids', JSON.stringify(ids)); }
  async function createTask() {
    const files=selectedFiles(), message=$('compare-upload-message');
    if (!files.length || files.some(x=>!x.left||!x.right)) { message.textContent='每组都需要同时选择左侧和右侧 DOCX。'; return; }
    const identity=state.identityToken;
    const name=($('compare-name').value||'合同对比').trim(); const pairs=files.map((x,i)=>{const leftId=`L${i}-${crypto.randomUUID()}`,rightId=`R${i}-${crypto.randomUUID()}`;return {client_pair_id:`P${i+1}`,label:`合同 ${i+1}`,left:{client_id:leftId,name:fileName(x.left),size:x.left.size},right:{client_id:rightId,name:fileName(x.right),size:x.right.size}};});
    const key=`compare-${Date.now()}-${crypto.randomUUID()}`; message.textContent='正在创建对比任务…'; $('compare-submit').disabled=true;
    try { const task=await json('/api/compare/tasks',{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':key},body:JSON.stringify({name,pairs})});
      if(identity!==state.identityToken)return;
      for (const [i,x] of files.entries()) { const form=new FormData(); markFiles(form,x,pairs[i]); const uploaded=await json(`/api/compare/tasks/${encodeURIComponent(task.id)}/uploads`,{method:'POST',body:form}); if(identity!==state.identityToken)return; const receipts=uploaded.receipts||[],bad=['left','right'].map(side=>receipts.find(r=>r.client_id===pairs[i][side].client_id)).filter(r=>!r||!['accepted','already_accepted'].includes(r.status)); if(bad.length) throw Error(`文件上传未完成：${bad.map(r=>r?`${r.client_id}（${r.error_code||r.status}）`:'缺少上传回执').join('、')}`); }
      await json(`/api/compare/tasks/${encodeURIComponent(task.id)}/seal`,{method:'POST'}); if(identity!==state.identityToken)return; message.textContent='已提交，对比任务正在处理。'; showCreate(false); await loadTasks(); await openTask(task.id);
    } catch(e) { if(identity===state.identityToken)message.textContent=`提交失败：${e.message}`; } finally { if(identity===state.identityToken)$('compare-submit').disabled=false; }
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
      const active=state.view.diffs[state.diffIndex]?.id,activeOnly=$('compare-active-only')?.checked,fragment=document.createDocumentFragment();
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
  function focusDiff(index) { const ds=state.view?.diffs||[]; if(!ds.length){ $('compare-diff-counter').textContent='0 / 0'; return; } state.diffIndex=(index+ds.length)%ds.length; const id=ds[state.diffIndex].id; document.querySelectorAll('.compare-diff.is-active,.compare-diff-item.is-active').forEach(n=>n.classList.remove('is-active')); document.querySelectorAll(`[data-diff-id="${CSS.escape(id)}"]`).forEach(n=>n.classList.add('is-active')); document.querySelector(`[data-compare-diff="${CSS.escape(id)}"]`)?.classList.add('is-active'); $('compare-diff-counter').textContent=`${state.diffIndex+1} / ${ds.length}`; for(const side of ['left','right']) { const pane=$(`compare-${side}-pane`), target=pane?.querySelector(`[data-diff-id="${CSS.escape(id)}"]`); if(pane&&target){const pr=pane.getBoundingClientRect(),tr=target.getBoundingClientRect(); pane.scrollTo({top:pane.scrollTop+(tr.top+tr.height/2)-(pr.top+pr.height/2),behavior:'smooth'});}} requestAnimationFrame(drawLines); }
  function renderViewer(payload) {
    state.view=payload; state.diffIndex=0; const d=payload.diffs||[]; $('compare-viewer').hidden=false; $('compare-pair-title').textContent=payload.pair?.label||'合同对比'; $('compare-left-name').textContent=payload.left?.name||'左侧合同'; $('compare-right-name').textContent=payload.right?.name||'右侧合同'; const s=payload.summary||{}; $('compare-summary').textContent=`共 ${s.total||0} 处差异 · 修改 ${s.modify||0} · 新增 ${s.insert||0} · 删除 ${s.delete||0}`; const cov=payload.coverage||{}; $('compare-coverage').hidden=cov.status==='complete'; $('compare-coverage').textContent=`覆盖范围：${cov.status||'incomplete'}${(cov.warnings||[]).length?' · '+cov.warnings.join('、'):''}`; $('compare-left-pane').innerHTML=payload.left.html||''; $('compare-right-pane').innerHTML=payload.right.html||''; $('compare-diff-counter').textContent='0 / 0'; $('compare-diff-list').innerHTML=d.length?d.map(x=>`<button type="button" class="compare-diff-item" data-compare-diff="${esc(x.id)}"><span>${esc(x.id)}</span><strong>${esc(x.type==='modify'?'修改':x.type==='insert'?'新增':'删除')}</strong><span>${esc(x.left_text||x.left?.text||'')} ${x.right_text||x.right?.text?'→ '+esc(x.right_text||x.right?.text):''}</span></button>`).join(''):'<p class="empty">两份合同没有文字差异。</p>'; drawLines();if(d.length)focusDiff(0); }
   async function openPair(index) { const p=state.pairs[index]; if(!p)return; const token=++state.requestToken; state.pairIndex=index; state.view=null; $('compare-viewer').hidden=true; $('compare-lines').replaceChildren(); $('compare-pair-counter').textContent=`${index+1} / ${state.pairs.length}`; if(!['succeeded','incomplete'].includes(p.status))return; try { const payload=await json(`/api/compare/pairs/${encodeURIComponent(p.id)}/view`); if(token===state.requestToken){p.viewError='';renderPairs();renderViewer(payload);} } catch(e) { if(token===state.requestToken){p.viewError=`读取结果失败：${e.message}`;renderPairs();} } }
  async function openTask(id) { clearTimeout(state.poll); const token=++state.requestToken; try { const task=await json(`/api/compare/tasks/${encodeURIComponent(id)}`); if(token!==state.requestToken)return; renderTask(task); const idx=state.pairs.findIndex(p=>['succeeded','incomplete'].includes(p.status)); if(idx>=0)await openPair(idx); else $('compare-viewer').hidden=true; if (['queued','running','uploading'].includes(state.task?.status)) { state.poll=setTimeout(()=>openTask(id),2500); } } catch(e) { if(token===state.requestToken)$('compare-task-status').textContent=`读取任务失败：${e.message}`; } }
  function bind() {
    $('compare-new')?.addEventListener('click',()=>showCreate(true)); $('compare-add-pair')?.addEventListener('click',()=>{const index=state.inputs.length;state.inputs.push({});$('compare-pair-inputs')?.insertAdjacentHTML('beforeend',pairRow({},index));syncInputIndexes();}); $('compare-submit')?.addEventListener('click',createTask); $('compare-refresh')?.addEventListener('click',loadTasks);
    $('compare-prev-diff')?.addEventListener('click',()=>focusDiff(state.diffIndex-1)); $('compare-next-diff')?.addEventListener('click',()=>focusDiff(state.diffIndex+1)); $('compare-prev-pair')?.addEventListener('click',()=>openPair(Math.max(0,state.pairIndex-1))); $('compare-next-pair')?.addEventListener('click',()=>openPair(Math.min(state.pairs.length-1,state.pairIndex+1))); $('compare-report')?.addEventListener('click',()=>{if(!state.view)return;const blob=new Blob([JSON.stringify(state.view,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`${state.task?.name||'合同对比'}-差异报告.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}); $('compare-active-only')?.addEventListener('change',drawLines);
    document.addEventListener('click',e=>{ const task=e.target.closest('[data-compare-task]');if(task){openTask(task.dataset.compareTask);return;}const pair=e.target.closest('[data-compare-pair]');if(pair){openPair(Number(pair.dataset.comparePair));return;}const diff=e.target.closest('[data-compare-diff]');if(diff){focusDiff((state.view?.diffs||[]).findIndex(x=>x.id===diff.dataset.compareDiff));return;}const remove=e.target.closest('[data-compare-remove]');if(remove){const index=Number(remove.dataset.compareRemove),row=remove.closest('.compare-pair-input');state.inputs.splice(index,1);row?.remove();if(!state.inputs.length){state.inputs=[{}];renderInputs();}else syncInputIndexes();return;} });
    document.addEventListener('change',e=>{const row=e.target.closest('.compare-pair-input');if(row&&e.target.matches('input[type=file]')){const i=Number(row.dataset.pairIndex),entry=state.inputs[i]||(state.inputs[i]={});entry[e.target.matches('[data-compare-left]')?'_left':'_right']=e.target.files?.[0]||null;row.querySelector('.compare-file-label').textContent=[entry._left?.name,entry._right?.name].filter(Boolean).join(' / ')||'尚未选择文件';return;}if(e.target.id==='compare-left-folder'||e.target.id==='compare-right-folder'){const side=e.target.id.includes('left')?'left':'right';state[`folder${side[0].toUpperCase()+side.slice(1)}`]=[...e.target.files].filter(f=>fileName(f).toLowerCase().endsWith('.docx')).sort((a,b)=>relativePath(a).localeCompare(relativePath(b)));const other=side==='left'?state.folderRight:state.folderLeft;if(!other?.length)return;const left=state.folderLeft||[],right=state.folderRight||[],map=new Map(right.map(f=>[relativePath(f),f])),used=new Set(),entries=left.map(f=>{const r=map.get(relativePath(f));if(r)used.add(r);return {_left:f,_right:r||null};});for(const f of right)if(!used.has(f))entries.push({_left:null,_right:f});state.inputs=entries;renderInputs();$('compare-upload-message').textContent=`已按相对路径配对 ${entries.filter(x=>x._left&&x._right).length} 组；${entries.filter(x=>!x._left||!x._right).length} 个文件未配对，可手工补齐。`;}});
    const cols=$('compare-columns'); if(cols){ for(const pane of [$('compare-left-pane'),$('compare-right-pane')])pane?.addEventListener('scroll',drawLines,{passive:true}); window.addEventListener('resize',drawLines); if(window.ResizeObserver)new ResizeObserver(drawLines).observe(cols); }
    document.addEventListener('fundlex:view',e=>{if(e.detail==='compare'){loadTasks();drawLines();}}); document.addEventListener('fundlex:identity-reset',()=>{clearTimeout(state.poll);state.identityToken++;state.listToken++;state.tasks=[];state.task=null;state.pairs=[];state.view=null;state.inputs=[{}];state.requestToken++;resetFolders();$('compare-create').hidden=true;$('compare-submit').disabled=false;$('compare-upload-message').textContent='';$('compare-name').value='';$('compare-detail').hidden=true;$('compare-viewer').hidden=true;$('compare-left-pane').innerHTML='';$('compare-right-pane').innerHTML='';$('compare-diff-list').innerHTML='';$('compare-lines').replaceChildren();$('compare-diff-counter').textContent='0 / 0';renderInputs();renderTasks();}); state.inputs=[{}];renderInputs(); loadTasks();
  }
  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded',bind); else bind();
})();
