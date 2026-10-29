(() => {
  'use strict';
  const api = window.FundLexWorkbench || {};
  const $ = id => document.getElementById(id);
  const esc = api.esc || (v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])));
  const state = { tasks: [], task: null, pairs: [], pairIndex: 0, selectedPairId: null, view: null, selection: null, selectionDraft: null, selectionDirty: false, selectionSaving: false, selectionToken: 0, selectionSaveToken: 0, poll: null, requestToken: 0, lineFrame: null, scrollFrame: null, scrollSource: null, identityToken: 0, listToken: 0, inputs: [{}], uploadDraft: null, splitRatio: .5, pendingSplitRatio: .5, splitDragging: false, leftMarks: null, rightMarks: null, mergedMarks: null, wordLeftMarks: null, wordRightMarks: null, viewMode: 'word', classicSide: 'left', classicRendered: false, wordSourcesRendered: false, diffPositions: null, docs: null, rawDocs: null };
  const SPLIT_KEY = 'fundlex-compare-split-ratio', SPLIT_GUTTER = 28;
  const clampSplitRatio = value => { const number = Number(value); return value !== null && value !== '' && Number.isFinite(number) ? Math.min(.8, Math.max(.2, number)) : .5; };
  function storedSplitRatio() { try { return clampSplitRatio(localStorage.getItem(SPLIT_KEY)); } catch { return .5; } }
  const json = (path, options) => api.json ? api.json(path, options) : fetch(path, options).then(async r => { if (!r.ok) throw Error(await r.text()); return r.json(); });
  Object.assign(state, { diffIndex: 0, selectionBusy: false, generationKey: null });
  const text = id => ($(id) || {}).textContent || '';
  const fileName = file => String(file?.name || '').replace(/\\/g, '/').split('/').pop();
  const legacyDoc = file => /\.doc$/i.test(fileName(file));
  const legacyDocMessage = files => `检测到 Word 97-2003 格式（.doc）文件：${files.map(fileName).join('、')}。请用 Word/WPS 打开后“另存为” .docx，再重新选择。`;
  const uploadErrorLabel = code => code==='LEGACY_DOC_UNSUPPORTED'?'请将 .doc 另存为 .docx':code;
  const relativePath = file => {
    const raw=String(file?.webkitRelativePath || '').replace(/\\/g, '/');
    if(raw) return raw.split('/').filter(Boolean).slice(1).join('/') || fileName(file);
    return fileName(file);
  };
  function pairRow(pair = {}, index) {
    const selected = [pair.left?.name || fileName(pair._left), pair.right?.name || fileName(pair._right)].filter(Boolean).join(' / ');
    const sideCard=(side,title,badge)=>{
      const name=pair[side]?.name||fileName(pair[`_${side}`]);
      return `<div class="compare-file-card ${name?'has-file':''}" data-file-side="${side}"><div class="compare-file-card-title"><span class="compare-side-badge">${badge}</span><strong>${title}</strong></div><div class="compare-file-name" title="${esc(name)}">${esc(name||'尚未选择合同')}</div><div class="compare-file-card-action"><button type="button" class="btn btn-sm" data-compare-choose="${side}" aria-label="选择${title}">${name?'更换文件':'选择文件'}</button><span>仅支持 DOCX</span></div><input type="file" accept=".doc,.docx,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document" data-compare-${side}="${index}" aria-label="${title}" hidden></div>`;
    };
    return `<div class="compare-pair-input" data-pair-index="${index}"><div class="compare-pair-head"><strong>合同组 ${String(index+1).padStart(2,'0')}</strong><button type="button" class="btn-link" data-compare-remove="${index}" ${index?'':'disabled'}>移除本组</button></div><div class="compare-side-inputs">${sideCard('left','合同A','A')}${sideCard('right','合同B','B')}</div><p class="sr-only compare-file-label" data-compare-label="${index}">${esc(selected||'尚未选择文件')}</p></div>`;
  }
  function renderInputs() { const box=$('compare-pair-inputs'); if (box) box.innerHTML = (state.inputs || [{}]).map(pairRow).join(''); }
  function syncInputIndexes() { document.querySelectorAll('#compare-pair-inputs .compare-pair-input').forEach((row,i)=>{ row.dataset.pairIndex=String(i); row.querySelector('[data-compare-left]')?.setAttribute('data-compare-left',String(i)); row.querySelector('[data-compare-right]')?.setAttribute('data-compare-right',String(i)); row.querySelector('[data-compare-remove]')?.setAttribute('data-compare-remove',String(i)); }); }
  function selectedFiles() { return (state.inputs || []).map(x => ({ left: x._left || x.left, right: x._right || x.right })).filter(x => x.left || x.right); }
  function resetFolders() { state.folderLeft=[]; state.folderRight=[]; for(const id of ['compare-left-folder','compare-right-folder'])if($(id))$(id).value=''; }
  function showCreate(show=true) { $('compare-create').hidden = !show; if (show) { clearTimeout(state.poll); state.requestToken++; $('compare-detail').hidden=true; setFullscreenViewer(false); state.view=null; state.mergedMarks=state.leftMarks=state.rightMarks=null; state.uploadDraft=null; state.inputs=[{}]; resetFolders(); $('compare-upload-message').textContent=''; $('compare-retry').hidden=true; $('compare-lines')?.replaceChildren(); for(const pane of [$('compare-word-merged-pane'),$('compare-word-left-pane'),$('compare-word-right-pane'),$('compare-left-pane'),$('compare-right-pane')]){clearVirtual(pane);if(pane)pane.innerHTML='';} renderInputs(); } }
  function statusLabel(v) { return ({pending:'待上传',queued:'排队中',leased:'处理中',running:'处理中',succeeded:'已处理',incomplete:'覆盖不完整',failed:'失败',retry_wait:'等待重试',sealed:'已提交',uploading:'上传中',completed:'已处理'}[v] || v || '—'); }
  function taskMetrics(task) {
    const pairs=task.pairs||[], counts=task.counts||{};
    const count=status=>pairs.length?pairs.filter(p=>p.status===status).length:(counts[status]||0);
    const failed=count('failed'), incomplete=count('incomplete');
    const pending=pairs.length?pairs.filter(p=>!['succeeded','incomplete','failed'].includes(p.status)).length:(counts.pending||0);
    const results=pairs.filter(p=>['succeeded','incomplete'].includes(p.status)&&Number.isInteger(p.summary?.total));
    const notes=[pending?`${pending} 组待处理`:'',failed?`${failed} 组失败`:'',incomplete?`${incomplete} 组覆盖不完整`:''].filter(Boolean);
    const total=results.reduce((sum,p)=>sum+p.summary.total,0);
    const differences=results.length?`${total} 处差异`:'暂无差异结果';
    const status=task.status==='completed'?(failed||incomplete?`已处理 · ${notes.join(' · ')}`:'已处理'):statusLabel(task.status);
    return {status,differences};
  }
  function renderTasks() {
    const box=$('compare-task-list'); if (!box) return;
    const route=api.route?.()||{},q=String(route.q||'').toLowerCase(),status=route.status||'';
    const matches=state.tasks.filter(t=>(!q||String(t.name).toLowerCase().includes(q))&&(!status||t.status===status)),max=Math.max(1,Math.ceil(matches.length/20)),page=Math.min(max,Math.max(1,Number(route.page)||1));
    $('compare-list-pagination').innerHTML=`<span>共 ${matches.length} 个任务 · 第 ${page} / ${max} 页</span><button class="btn btn-sm" type="button" data-compare-list-page="${page-1}" ${page<=1?'disabled':''}>上一页</button><button class="btn btn-sm" type="button" data-compare-list-page="${page+1}" ${page>=max?'disabled':''}>下一页</button>`;
    if(!matches.length){box.innerHTML='<div class="empty"><strong>当前条件下没有比对任务</strong><p>新建一组或多组合同开始比较，或调整筛选条件。</p></div>';return;}
    box.innerHTML=`<div class="table-wrap"><table class="table"><thead><tr><th>任务</th><th>合同组</th><th>状态</th><th>差异</th><th></th></tr></thead><tbody>${matches.slice((page-1)*20,page*20).map(t=>{const m=taskMetrics(t);return `<tr><td>${esc(t.name)}</td><td>${t.total||0}</td><td>${esc(m.status)}</td><td>${esc(m.differences)}</td><td><button type="button" class="btn btn-sm" data-compare-task="${esc(t.id)}">查看</button></td></tr>`;}).join('')}</tbody></table></div>`;
  }
  async function loadTasks() { const token=++state.listToken,identity=state.identityToken; try { const p=await json('/api/compare/tasks'); if(token!==state.listToken||identity!==state.identityToken)return; state.tasks=p.items||[]; renderTasks(); } catch (e) { if(token===state.listToken&&identity===state.identityToken)$('compare-task-list').innerHTML=`<p class="field-error">读取对比任务失败：${esc(e.message)}</p>`; } }
  function renderTask(task) {
    state.task=task; state.pairs=task.pairs||[]; $('compare-detail').hidden=false; $('compare-task-name').textContent=task.name||'未命名任务';api.setObjectTitle?.('compare',task.name); $('compare-task-status').textContent=`${taskMetrics(task).status} · ${state.pairs.length} 组`;
    state.tasks=state.tasks.map(t=>t.id===task.id?task:t); renderTasks(); renderPairs();
  }
  function renderPairs() {
    $('compare-pair-list').innerHTML=`<div class="compare-pair-statuses">${state.pairs.map((p,i)=>`<button type="button" class="compare-pair-status ${p.id===state.selectedPairId?'is-selected':''} ${['succeeded','incomplete'].includes(p.status)?'is-done':''} ${p.status==='incomplete'?'is-incomplete':''} ${p.status==='failed'||p.viewError?'is-failed':''}" data-compare-pair="${i}"><span class="compare-pair-number">${String(i+1).padStart(2,'0')}</span><span class="compare-pair-main"><strong>${esc(p.label||`第 ${i+1} 组`)}</strong><small>合同A：${esc(p.left?.name||'未命名')} / 合同B：${esc(p.right?.name||'未命名')}</small></span><span class="compare-pair-state">${esc(statusLabel(p.status))}${p.summary?` · ${p.summary.total} 处`:''}</span>${p.error_code||p.viewError?`<span class="compare-pair-error" role="status">${esc(p.viewError||`处理失败：${p.error_code}`)}</span>`:''}</button>`).join('')}</div>`;
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
        if(bad.length)throw Error(`第 ${i+1} 组上传未完成：${bad.map(r=>r?`${r.client_id}（${uploadErrorLabel(r.error_code)||r.status}）`:'缺少上传回执').join('、')}`);
        draft.next=i+1;
      }
      message.textContent='文件已上传，正在提交对比任务…'; await json(`/api/compare/tasks/${encodeURIComponent(draft.task.id)}/seal`,{method:'POST'}); if(identity!==state.identityToken)return;
      message.textContent='已提交，对比任务正在处理。'; state.uploadDraft=null; showCreate(false); await loadTasks(); await openTask(draft.task.id);
    } catch(e) { if(identity===state.identityToken){message.textContent=`上传中断：${e.message}。已完成的文件已保留，可点击“继续上传”。`; $('compare-retry').hidden=false;} }
    finally { if(identity===state.identityToken)$('compare-submit').disabled=false; }
  }
  async function createTask() {
    const files=selectedFiles(), message=$('compare-upload-message');
    const legacy=files.flatMap(x=>[x.left,x.right]).filter(f=>f&&legacyDoc(f));
    if(legacy.length){message.textContent=legacyDocMessage(legacy);return;}
    if (!files.length || files.some(x=>!x.left||!x.right)) { message.textContent='每组都需要同时选择合同A和合同B的 DOCX 文件。'; return; }
    const identity=state.identityToken; const name=($('compare-name').value||'合同比对').trim(); const pairs=files.map((x,i)=>{const leftId=`L${i}-${crypto.randomUUID()}`,rightId=`R${i}-${crypto.randomUUID()}`;return {client_pair_id:`P${i+1}`,label:`合同 ${i+1}`,left:{client_id:leftId,name:fileName(x.left),size:x.left.size},right:{client_id:rightId,name:fileName(x.right),size:x.right.size}};});
    const key=`compare-${Date.now()}-${crypto.randomUUID()}`; message.textContent='正在创建对比任务…'; $('compare-submit').disabled=true;
    try { const task=await json('/api/compare/tasks',{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':key},body:JSON.stringify({name,pairs})}); if(identity!==state.identityToken)return; state.uploadDraft={task,pairs,files,next:0}; await continueUploads(); }
    catch(e) { if(identity===state.identityToken){message.textContent=`创建任务失败：${e.message}`;$('compare-submit').disabled=false;} }
  }
  function blockFor(side, id) { return document.querySelector(`#compare-${side}-pane [data-block-id="${CSS.escape(id)}"]`); }
  function targetFor(side, span, item) { const pane=$(`compare-${side}-pane`); if(!pane)return null; const id=span?.block_id || item?.[`${side}_anchor`]?.block_id; return id ? blockFor(side,id) : pane.querySelector('.compare-block'); }
  function applySplitRatio(value, persist = true) {
    const ratio = clampSplitRatio(value), cols=$('compare-columns'), head=$('compare-columns-head'), gutter=$('compare-gutter');
    if (!cols) return;
    state.diffPositions = null;
    state.splitRatio = ratio;
    cols.style.gridTemplateColumns = `${ratio}fr ${SPLIT_GUTTER}px ${1 - ratio}fr`;
    if (head) head.style.gridTemplateColumns = `${ratio}fr ${SPLIT_GUTTER}px ${1 - ratio}fr`;
    if (gutter) {
      const percent = Math.round(ratio * 100);
      gutter.setAttribute('aria-valuenow', String(percent));
      gutter.setAttribute('aria-valuetext', `${percent}% / ${100 - percent}%`);
    }
    if (persist) { try { localStorage.setItem(SPLIT_KEY, String(ratio)); } catch {} }
    if (!state.splitDragging) drawLines();
  }
  function bindCompareSplitter() {
    const gutter=$('compare-gutter'), cols=$('compare-columns'); if (!gutter || !cols) return;
    let dragging = false, dragLeft = 0, dragUsable = 1;
    const preview = $('compare-split-preview');
    const ratioAt = event => clampSplitRatio((event.clientX - dragLeft - SPLIT_GUTTER / 2) / dragUsable);
    const showPreview = ratio => {
      if (!preview) return;
      preview.style.left = `${dragUsable * ratio + SPLIT_GUTTER / 2}px`;
      const percent = Math.round(ratio * 100);
      gutter.setAttribute('aria-valuenow', String(percent));
      gutter.setAttribute('aria-valuetext', `${percent}% / ${100 - percent}%`);
    };
    const move = event => {
      if (!dragging) return;
      event.preventDefault(); state.pendingSplitRatio = ratioAt(event); showPreview(state.pendingSplitRatio);
    };
    const finish = apply => {
      if (!dragging) return;
      dragging = false; state.splitDragging = false;
      gutter.classList.remove('is-dragging');
      if (preview) { preview.style.left = ''; preview.style.opacity = ''; }
      window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', onUp); window.removeEventListener('pointercancel', onCancel);
      applySplitRatio(apply ? state.pendingSplitRatio : state.splitRatio, true); refreshVirtualLayouts(); drawLines();
    };
    const onUp = () => finish(true);
    const onCancel = () => finish(false);
    gutter.addEventListener('pointerdown', event => {
      if (event.button !== 0 || window.matchMedia('(max-width: 760px)').matches) return;
      event.preventDefault(); const rect = cols.getBoundingClientRect();
      dragLeft = rect.left; dragUsable = Math.max(1, rect.width - SPLIT_GUTTER);
      dragging = true; state.splitDragging = true; state.pendingSplitRatio = state.splitRatio;
      gutter.classList.add('is-dragging');
      if (preview) preview.style.opacity = '1';
      showPreview(state.splitRatio);
      window.addEventListener('pointermove', move); window.addEventListener('pointerup', onUp); window.addEventListener('pointercancel', onCancel);
    });
    gutter.addEventListener('dblclick', () => applySplitRatio(.5));
    gutter.addEventListener('keydown', event => {
      const step = event.shiftKey ? .05 : .02; let next = state.splitRatio;
      if (event.key === 'ArrowLeft') next -= step;
      else if (event.key === 'ArrowRight') next += step;
      else if (event.key === 'Home') next = .2;
      else if (event.key === 'End') next = .8;
      else if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); applySplitRatio(.5); return; }
      else return;
      event.preventDefault(); applySplitRatio(next);
    });
    applySplitRatio(storedSplitRatio(), false);
  }
  function refreshDiffMarks() {
    const marks = id => {
      const pane = $(id);
      return pane ? new Map([...pane.querySelectorAll('[data-diff-id]')].map(n => [n.dataset.diffId, n])) : null;
    };
    state.mergedMarks = marks('compare-word-merged-pane');
    state.wordLeftMarks = marks('compare-word-left-pane');
    state.wordRightMarks = marks('compare-word-right-pane');
    state.leftMarks = marks('compare-left-pane');
    state.rightMarks = marks('compare-right-pane');
  }
  function cacheDiffPositions() {
    if(!state.view||!state.leftMarks||!state.rightMarks)return;
    const left=$('compare-left-pane'),right=$('compare-right-pane'); if(!left||!right)return;
    const lr=left.getBoundingClientRect(),rr=right.getBoundingClientRect(),positions=[];
    for(const d of state.view.diffs||[]){
      const l=state.leftMarks.get(d.id),r=state.rightMarks.get(d.id); if(!l||!r)continue;
      const a=l.getBoundingClientRect(),b=r.getBoundingClientRect();
      positions.push({id:d.id,leftY:a.top-lr.top+left.scrollTop,rightY:b.top-rr.top+right.scrollTop,leftH:a.height,rightH:b.height,leftX:a.right-lr.left,rightX:b.left-rr.left});
    }
    state.diffPositions=positions;
  }
  function drawLines() {
    if(state.lineFrame!==null)return;
    state.lineFrame=requestAnimationFrame(()=>{
      state.lineFrame=null;
      const classic=$('compare-classic-view');
      if(!classic||classic.hidden||!state.view||$('compare-viewer').hidden)return;
      const cols=$('compare-columns'),svg=$('compare-lines'); if(!cols||!svg)return;
      const cr=cols.getBoundingClientRect(); if(!cr.width||!cr.height)return;
      const left=$('compare-left-pane'),right=$('compare-right-pane'); if(!left||!right)return;
      const lr=left.getBoundingClientRect(),rr=right.getBoundingClientRect();
      if(!state.diffPositions)cacheDiffPositions();
      if(!state.diffPositions)return;
      const active=visibleDiffs()[state.diffIndex]?.id;
      const leftTop=left.scrollTop,leftBottom=leftTop+left.clientHeight,rightTop=right.scrollTop,rightBottom=rightTop+right.clientHeight;
      const fragment=document.createDocumentFragment(); let count=0;
      for(const p of state.diffPositions){
        if(p.id!==active){
          const above=p.leftY+p.leftH<leftTop-80&&p.rightY+p.rightH<rightTop-80;
          const below=p.leftY>leftBottom+80&&p.rightY>rightBottom+80;
          if(above||below)continue;
        }
        const x1=lr.left-cr.left+p.leftX,y1=lr.top-cr.top+(p.leftY-leftTop)+p.leftH/2;
        const x2=rr.left-cr.left+p.rightX,y2=rr.top-cr.top+(p.rightY-rightTop)+p.rightH/2;
        if(p.id!==active&&((y1<-40&&y2<-40)||(y1>cr.height+40&&y2>cr.height+40)))continue;
        const path=document.createElementNS('http://www.w3.org/2000/svg','path');
        path.setAttribute('d',`M ${x1} ${y1} C ${(x1+x2)/2} ${y1}, ${(x1+x2)/2} ${y2}, ${x2} ${y2}`);
        path.dataset.diffId=p.id;path.classList.toggle('active',p.id===active);fragment.append(path);
        if(++count>=240)break;
      }
      svg.setAttribute('viewBox',`0 0 ${cr.width} ${cr.height}`);
      svg.replaceChildren(fragment);
    });
  }
  function visiblePanels() {
    return allPanels().filter(pane => pane.offsetParent !== null && pane.clientHeight > 0);
  }
  function syncPaneScroll(source) {
    if(state.focusScrolling){drawLines();return;}
    if (window.matchMedia('(max-width: 760px)').matches) { drawLines(); return; }
    if (state.scrollSource && state.scrollSource !== source) { drawLines(); return; }
    const targets = visiblePanels().filter(p => p !== source);
    if (!targets.length) return;
    state.scrollSource = source;
    cancelAnimationFrame(state.scrollFrame);
    state.scrollFrame = requestAnimationFrame(() => {
      const sourceMax = Math.max(0, source.scrollHeight - source.clientHeight);
      const ratio = sourceMax ? source.scrollTop / sourceMax : 0;
      targets.forEach(target => {
        const targetMax = Math.max(0, target.scrollHeight - target.clientHeight);
        target.scrollTop = ratio * targetMax;
      });
      drawLines();
      state.scrollFrame = requestAnimationFrame(() => { state.scrollSource = null; state.scrollFrame = null; drawLines(); });
    });
  }
  function normalizeSelection(payload) {
    if(!payload)return null;
    const draft=payload.draft&&typeof payload.draft==='object'?payload.draft:null;
    const legacy=payload.selection&&typeof payload.selection==='object'?payload.selection:null;
    const epoch=Number.isInteger(legacy?.selection_epoch)?legacy.selection_epoch:Number.isInteger(payload.selection_epoch)?payload.selection_epoch:Number.isInteger(draft?.selection_epoch)?draft.selection_epoch:0;
    const decisions=legacy?.decisions&&typeof legacy.decisions==='object'?legacy.decisions:payload.decisions&&typeof payload.decisions==='object'?payload.decisions:draft?.decisions&&typeof draft.decisions==='object'?draft.decisions:{};
    const artifacts=[];
    for(const version of payload.artifacts||[]){
      if(version&&version.files&&typeof version.files==='object'){
        for(const [kind,file] of Object.entries(version.files)){if(file&&file.download_url)artifacts.push({...file,kind,version:version.version,status:version.current?'current':version.stale?'stale':'history',report:version.report||null});}
      }else if(version&&version.download_url)artifacts.push(version);
    }
    return {...payload,selection_epoch:epoch,decisions,selection:{selection_epoch:epoch,decisions},artifacts};
  }
  function selectionDecision(id) { return state.selectionDraft?.[id] || state.selection?.decisions?.[id] || 'pending'; }
  function syncSelectionControls() {
    const disabled=!state.selection||state.selectionSaving;
    document.querySelectorAll('#compare-diff-list .compare-diff-item').forEach(item=>{
      const id=item.dataset.compareDiff; if(!id)return;
      const choice=selectionDecision(id);
      item.classList.toggle('is-selected-choice',choice!=='pending');
      item.querySelectorAll('[data-selection-choice]').forEach(input=>{
        const checked=input.value===choice; input.checked=checked; input.disabled=disabled;
        input.closest('label')?.classList.toggle('is-checked',checked);
      });
    });
  }
  function updateSelectionItem(id) {
    const item=document.querySelector(`.compare-diff-item[data-compare-diff="${CSS.escape(id)}"]`); if(!item)return;
    const choice=selectionDecision(id), disabled=!state.selection||state.selectionSaving;
    item.classList.toggle('is-selected-choice',choice!=='pending');
    item.querySelectorAll('[data-selection-choice]').forEach(input=>{
      const checked=input.value===choice; input.checked=checked; input.disabled=disabled;
      input.closest('label')?.classList.toggle('is-checked',checked);
    });
  }
  function selectionBinding() { const s=state.selection; if(!s)return null; return {expected_epoch:Number.isInteger(s.selection_epoch)?s.selection_epoch:0,result_sha256:s.result_sha256,left_source_sha256:s.left_source_sha256,right_source_sha256:s.right_source_sha256}; }
  function selectionStatus(message, error=false) { const node=$('compare-selection-status'); if(node){node.textContent=message||'';node.classList.toggle('is-error',!!error);} }
  function selectionCounts() { const ds=state.view?.diffs||[], counts={pending:0,left:0,right:0}; ds.forEach(d=>{const value=selectionDecision(d.id);if(counts[value]!==undefined)counts[value]++;}); return {counts,total:ds.length,pending:counts.pending}; }
  function selectionIssues() {
    return [...(state.selection?.assessment?.issues||[])];
  }
  function selectionCanGenerate() { return !!state.selection&&!state.selectionDirty&&!state.selectionSaving&&!state.selectionBusy&&!selectionCounts().pending&&!selectionIssues().some(x=>x.blocking); }
  function selectionContext() { return {pairId:state.selectedPairId,token:state.selectionToken,identity:state.identityToken}; }
  function selectionCurrent(context) { return context.pairId===state.selectedPairId&&context.token===state.selectionToken&&context.identity===state.identityToken; }
  function resetSelection() {
    state.selectionToken++;state.selectionSaveToken++;state.selection=null;state.selectionDraft=null;
    state.selectionDirty=false;state.selectionSaving=false;state.selectionBusy=false;state.generationKey=null;
    selectionStatus('');$('compare-selection-downloads')?.replaceChildren();renderSelection();syncSelectionControls();
  }
  function renderSelectionDownloads() {
    const box=$('compare-selection-downloads'); if(!box)return;
    const artifacts=state.selectionDirty?[]:(state.selection?.artifacts||[]);
    if(!artifacts.length){box.replaceChildren();return;}
    const labels={selected_final:'下载选择结果 DOCX',selected_redline:'下载选择结果（带修订痕迹）DOCX',selection_report_markdown:'下载选择报告（Markdown）',selection_report_json:'下载选择报告（JSON）'};
    box.innerHTML=artifacts.map(item=>`<div class="compare-artifact"><button class="btn btn-sm" type="button" data-selection-download="${esc(item.download_url)}" data-selection-filename="${esc(`compare-v${item.version}-${item.kind}${item.kind.endsWith('docx')?'.docx':''}`)}" ${item.status==='stale'?'title="该版本已过期，仅作追溯"':''}>${esc(labels[item.kind]||item.kind)} · v${item.version}${item.status==='stale'?' · 已过期':''}</button><small>SHA-256：${esc(item.sha256)}</small></div>`).join('');
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
    if(generate){generate.disabled=!ready;generate.title=pending?'所有差异都需要明确选择合同A或合同B':blocked?'当前结果包含暂不支持的结构':'生成选择结果';}
    buttons.forEach(x=>{if(x!==preview&&x!==generate)x.disabled=busy;});
    $('compare-selection-save').disabled=busy||!state.selectionDirty;
    $('compare-selection-pending').disabled=busy||!pending;
    for(const side of ['left','right'])$(`compare-selection-${side}-all`).textContent=`全部采用 ${side==='left'?'A':'B'}`;
    renderSelectionDownloads();
  }
  async function loadSelection(pairId) {
    resetSelection();const token=state.selectionToken;
    try { const payload=await json(`/api/compare/pairs/${encodeURIComponent(pairId)}/selection`); if(token!==state.selectionToken||pairId!==state.selectedPairId)return; state.selection=normalizeSelection(payload);state.selectionDraft={...(state.selection?.decisions||{})};renderSelection();syncSelectionControls(); }
    catch(e){if(token===state.selectionToken){selectionStatus(`读取选择状态失败：${e.message}`,true);renderSelection();}}
  }
  async function saveSelectionDraft(updateIds) {
    const binding=selectionBinding(); if(!binding||!state.selectionDraft)return;
    if(state.selectionSaving||state.selectionBusy)return;
    const context=selectionContext(), token=++state.selectionSaveToken, decisions={...state.selectionDraft};
    state.selectionSaving=true;state.selectionDirty=true;selectionStatus('正在保存选择…');renderSelection();if(updateIds)updateIds.forEach(updateSelectionItem);else syncSelectionControls();
    try {
      const payload=await json(`/api/compare/pairs/${encodeURIComponent(context.pairId)}/selection`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({...binding,decisions})});
      if(!selectionCurrent(context)||token!==state.selectionSaveToken)return;
      state.selection=normalizeSelection(payload);state.selectionDraft={...(state.selection?.decisions||{})};state.selectionDirty=false;state.generationKey=null;selectionStatus('已保存');
    } catch(e) {
      if(!selectionCurrent(context)||token!==state.selectionSaveToken)return;
      if(e.raw==='SELECTION_EPOCH_CONFLICT') {
        try {
          const latest=await json(`/api/compare/pairs/${encodeURIComponent(context.pairId)}/selection`);
          if(!selectionCurrent(context)||token!==state.selectionSaveToken)return;
          if(['result_sha256','left_source_sha256','right_source_sha256'].every(k=>latest[k]===state.selection[k]))state.selection=normalizeSelection(latest);
        } catch { /* Keep the local map; a failed reload must not discard it. */ }
      }
      if(selectionCurrent(context)){state.selectionDirty=true;selectionStatus('保存未完成，本地选择已保留。请核对后点击“保存当前选择”重试。',true);}
    } finally {if(selectionCurrent(context)&&token===state.selectionSaveToken){state.selectionSaving=false;renderSelection();if(updateIds)updateIds.forEach(updateSelectionItem);else syncSelectionControls();}}
  }
  function chooseSelection(id, choice) { if(!state.selection||state.selectionSaving||state.selectionBusy)return; state.selectionDraft={...(state.selectionDraft||{}),[id]:choice};state.selectionDirty=true;updateSelectionItem(id);saveSelectionDraft([id]); }
  function setAllSelections(choice) { if(!state.selection||state.selectionSaving||state.selectionBusy)return; const next={};(state.view?.diffs||[]).forEach(item=>{next[item.id]=choice;});state.selectionDraft=next;state.selectionDirty=true;syncSelectionControls();saveSelectionDraft(); }
  async function selectionAction(kind) {
    const binding=selectionBinding();if(!binding||state.selectionSaving||state.selectionBusy||state.selectionDirty||(kind==='generate'&&!selectionCanGenerate()))return;
    const context=selectionContext();state.selectionBusy=true;
    selectionStatus(kind==='generate'?'正在生成选择结果 DOCX，请稍候…':'正在检查生成条件…');renderSelection();syncSelectionControls();
    const headers={'Content-Type':'application/json'};
    if(kind==='generate'){state.generationKey ||= `compare-${crypto.randomUUID()}`;headers['Idempotency-Key']=state.generationKey;}
    try {
      const body=kind==='preview'?{decisions:{...state.selectionDraft}}
        :{expected_epoch:binding.expected_epoch,decision_hash:state.selection?.draft?.decision_hash||state.selection?.decision_hash||'',result_sha256:binding.result_sha256};
      const result=await json(`/api/compare/pairs/${encodeURIComponent(context.pairId)}/selection/${kind}`,{method:'POST',headers,body:JSON.stringify(body)});
      if(!selectionCurrent(context))return;
      if(kind==='generate'){
        const latest=normalizeSelection(await json(`/api/compare/pairs/${encodeURIComponent(context.pairId)}/selection`));
        if(!selectionCurrent(context))return;
        state.selection=latest;state.selectionDraft={...(latest?.decisions||{})};state.selectionDirty=false;state.generationKey=null;
        selectionStatus(`已生成版本 ${result.version}，可下载选择结果、带修订痕迹的选择结果和报告。`);
      }
      else {state.selection={...state.selection,assessment:result.assessment};const pending=result.assessment.pending_ids.length,blocked=selectionIssues().some(x=>x.blocking);selectionStatus(pending?`仍有 ${pending} 处待选择，全部明确选择后才能生成。`:blocked?'当前结果包含暂不支持的结构，请查看说明。':'当前选择可以提交生成；生成时还会校验 DOCX 结构。',!!(pending||blocked));}
    } catch(e){if(selectionCurrent(context))selectionStatus(e.raw||e.message,true);}
    finally {if(selectionCurrent(context)){state.selectionBusy=false;renderSelection();syncSelectionControls();}}
  }
  const previewSelection=()=>selectionAction('preview'), generateSelection=()=>selectionAction('generate');
  async function downloadSelection(url, filename) {
    const context=selectionContext();
    try {
      if(typeof api.download!=='function')throw new Error('下载暂不可用，请刷新页面后重试。');
      await api.download(url,filename);
      if(selectionCurrent(context))selectionStatus('下载已开始。');
    } catch(e){if(selectionCurrent(context))selectionStatus(e.message,true);}
  }
  const WORD_PANES = ['compare-word-merged-pane','compare-word-left-pane','compare-word-right-pane'];
  const CLASSIC_PANES = ['compare-left-pane','compare-right-pane'];
  function allPanels() { return [...WORD_PANES, ...CLASSIC_PANES].map(id => $(id)).filter(Boolean); }
  function setViewMode(mode, persist=true) {
    const next = mode === 'classic' ? 'classic' : 'word';
    state.viewMode = next;
    const viewer = $('compare-viewer'), body = $('compare-view-body');
    if (viewer) viewer.dataset.viewMode = next;
    if (body) body.dataset.viewMode = next;
    const word = $('compare-word-view'), classic = $('compare-classic-view');
    if (word) word.hidden = next !== 'word';
    if (classic) classic.hidden = next !== 'classic';
    document.querySelectorAll('[data-compare-view-mode]').forEach(button => {
      const active = button.dataset.compareViewMode === next;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    if (persist) { try { localStorage.setItem('fundlex-compare-view-mode', next); } catch {} }
    if (next === 'classic' && state.view && !state.classicRendered) renderClassicView();
    if (next === 'word' && state.view && !state.wordSourcesRendered) renderWordSources();
    if (next === 'classic') applySplitRatio(state.splitRatio, false);
    requestAnimationFrame(() => { drawLines(); if (state.view) focusDiff(state.diffIndex); });
  }
  function setClassicSide(side, persist=true) {
    const next = side === 'right' ? 'right' : 'left';
    state.classicSide = next;
    const viewer = $('compare-viewer');
    if (viewer) viewer.dataset.mobileSide = next;
    document.querySelectorAll('#compare-classic-view [data-compare-side]').forEach(button => {
      const active = button.dataset.compareSide === next;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    if (persist) { try { localStorage.setItem('fundlex-compare-classic-side', next); } catch {} }
    if (state.view) requestAnimationFrame(() => focusDiff(state.diffIndex));
  }
  function setMobilePane(pane, persist=true) {
    const next = ['merged','left','right'].includes(pane) ? pane : 'merged';
    if(next!=='merged'&&$('compare-word-layout')?.classList.contains('is-sources-hidden'))setSourcesVisible(true,false);
    const viewer = $('compare-viewer'); if (viewer) viewer.dataset.mobilePane = next;
    document.querySelectorAll('[data-word-pane]').forEach(button => {
      const active = button.dataset.wordPane === next;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    if (persist) { try { localStorage.setItem('fundlex-compare-mobile-pane', next); } catch {} }
  }
  function setSourcesVisible(show, persist=true) {
    const layout = $('compare-word-layout'); if (!layout) return;
    layout.classList.toggle('is-sources-hidden', !show);
    const toggle = $('compare-show-sources'); if (toggle) toggle.checked = show;
    if (show && state.view && !state.wordSourcesRendered) renderWordSources();
    if (persist) { try { localStorage.setItem('fundlex-compare-show-sources', show ? '1' : '0'); } catch {} }
    requestAnimationFrame(() => { if(show){const merged=$('compare-word-merged-pane');if(merged)syncPaneScroll(merged);} drawLines(); });
  }
  function setMarkupMode(mode, persist=true) {
    const layout = $('compare-word-layout'); if (!layout) return;
    const next = ['all','simple','final'].includes(mode) ? mode : 'all';
    layout.dataset.markup = next;
    const select = $('compare-markup-mode'); if (select) select.value = next;
    if (persist) { try { localStorage.setItem('fundlex-compare-markup', next); } catch {} }
  }
  function visibleDiffs() { const all=state.view?.diffs||[], filter=$('compare-diff-filter')?.value||''; return filter?all.filter(x=>x.type===filter):all; }
  function paneHasTarget(paneId, selector) { return Boolean($(paneId)?.querySelector(selector)); }
  function markActiveDiff() {
    const item=visibleDiffs()[state.diffIndex]; if(!item)return;
    const selector=`[data-diff-id="${CSS.escape(item.id)}"]`;
    document.querySelectorAll([...WORD_PANES,...CLASSIC_PANES].map(pane=>`#${pane} ${selector}`).join(',')).forEach(node=>node.classList.add('is-active'));
    document.querySelector(`.compare-diff-item[data-compare-diff="${CSS.escape(item.id)}"]`)?.classList.add('is-active');
  }
  function focusDiff(index) {
    const ds=visibleDiffs();
    document.querySelectorAll('.compare-diff.is-active,.compare-diff-item.is-active').forEach(n=>n.classList.remove('is-active'));
    if(!ds.length){$('compare-diff-counter').textContent='0 / 0';return;}
    state.diffIndex=(index+ds.length)%ds.length;const id=ds[state.diffIndex].id,diff=ds[state.diffIndex];
    const selector=`[data-diff-id="${CSS.escape(id)}"]`;
    const paneIds=[...WORD_PANES,...CLASSIC_PANES];
    const blockFor=side=>{
      const span=side==='left'?diff.left:diff.right;
      const anchor=side==='left'?diff.left_anchor:diff.right_anchor;
      const spans=side==='left'?diff.left_spans:diff.right_spans;
      return span?.block_id||anchor?.block_id||spans?.[0]?.block_id||'';
    };
    const findBlock=(paneId,side)=>{
      const pane=$(paneId);if(!pane||!pane._virtualDoc||!pane.clientHeight)return;
      const blockId=blockFor(side)||blockFor(side==='left'?'right':'left');
      if(blockId)pane._virtualDoc.scrollToBlock(blockId);
    };
    findBlock('compare-word-merged-pane','right');findBlock('compare-word-left-pane','left');findBlock('compare-word-right-pane','right');
    findBlock('compare-left-pane','left');findBlock('compare-right-pane','right');
    document.querySelectorAll(paneIds.map(pane=>`#${pane} ${selector}`).join(',')).forEach(n=>n.classList.add('is-active'));
    const list=$('compare-diff-list');
    if(list&&state.diffList?.length&&(!state.diffWindow||state.diffIndex<state.diffWindow.start||state.diffIndex>=state.diffWindow.end)){
      const desired=Math.max(0,state.diffIndex*DIFF_ITEM_HEIGHT-(list.clientHeight-DIFF_ITEM_HEIGHT)/2);
      list.scrollTop=desired;renderDiffWindow(Math.max(0,Math.floor(desired/DIFF_ITEM_HEIGHT)-4));
    }
    const item=document.querySelector(`.compare-diff-item[data-compare-diff="${CSS.escape(id)}"]`);
    item?.classList.add('is-active');
    if(item&&list){const ir=item.getBoundingClientRect(),lr=list.getBoundingClientRect();if(ir.top<lr.top||ir.bottom>lr.bottom)list.scrollTop+=ir.top-lr.top;}
    $('compare-diff-counter').textContent=`${state.diffIndex+1} / ${ds.length}`;
    if(matchMedia('(max-width:760px)').matches){
      if(state.viewMode==='word'){
        const currentId=state.mobilePane==='left'?'compare-word-left-pane':state.mobilePane==='right'?'compare-word-right-pane':'compare-word-merged-pane';
        if(!paneHasTarget(currentId,selector)){
          const candidates=[['merged','compare-word-merged-pane'],['right','compare-word-right-pane'],['left','compare-word-left-pane']];
          const next=candidates.find(([,paneId])=>paneHasTarget(paneId,selector));
          if(next)setMobilePane(next[0],false);
        }
      } else {
        const currentId=state.classicSide==='right'?'compare-right-pane':'compare-left-pane';
        if(!paneHasTarget(currentId,selector)){
          const otherId=state.classicSide==='right'?'compare-left-pane':'compare-right-pane';
          if(paneHasTarget(otherId,selector))setClassicSide(state.classicSide==='right'?'left':'right',false);
        }
      }
    }
    cancelAnimationFrame(state.scrollFrame);state.scrollSource=null;state.focusScrolling=true;
    for(const paneId of paneIds){const pane=$(paneId),target=pane?.querySelector(selector);if(pane&&target&&pane.clientHeight){const pr=pane.getBoundingClientRect(),tr=target.getBoundingClientRect();pane.scrollTop+=tr.top+tr.height/2-pr.top-pr.height/2;}}
    requestAnimationFrame(()=>requestAnimationFrame(()=>{state.focusScrolling=false;}));
    requestAnimationFrame(drawLines);
  }
  const DIFF_ITEM_HEIGHT=128, DIFF_RENDER_COUNT=24;
  function diffItemHtml(x,index,choice,disabled){
    const kind=x.type==='modify'?'修改':x.type==='insert'?'插入':'删除';
    return `<div class="compare-diff-item ${choice!=='pending'?'is-selected-choice':''}" data-compare-diff="${esc(x.id)}"><button type="button" class="compare-diff-jump" data-compare-diff="${esc(x.id)}"><span class="compare-diff-index">${index+1}</span><span class="compare-diff-kind is-${esc(x.type)}">${esc(kind)}</span><span class="compare-diff-preview"><small>FundLex 对比</small><span>${esc(x.section||'正文')} · ${esc(x.left?.text||'')} ${x.right?.text?'→ '+esc(x.right.text):''}</span></span></button><div class="compare-choice" role="group" aria-label="${esc(x.id)} 采用 A 或 B"><label class="${choice==='left'?'is-checked':''}"><input type="radio" name="choice-${esc(x.id)}" value="left" data-selection-choice="left" data-diff-id="${esc(x.id)}" ${choice==='left'?'checked':''} ${disabled?'disabled':''}>采用 A</label><label class="${choice==='right'?'is-checked':''}"><input type="radio" name="choice-${esc(x.id)}" value="right" data-selection-choice="right" data-diff-id="${esc(x.id)}" ${choice==='right'?'checked':''} ${disabled?'disabled':''}>采用 B</label></div></div>`;
  }
  function renderDiffWindow(start){
    const list=$('compare-diff-list'),items=state.diffList||[];if(!list)return;
    if(!items.length){list.innerHTML='<p class="empty">当前筛选条件下没有差异。</p>';state.diffWindow={start:0,end:0};return;}
    const safeStart=Math.max(0,Math.min(items.length-1,start)),end=Math.min(items.length,safeStart+DIFF_RENDER_COUNT);
    const disabled=!state.selection||state.selectionSaving;
    const html=items.slice(safeStart,end).map((item,offset)=>diffItemHtml(item,safeStart+offset,selectionDecision(item.id),disabled)).join('');
    list.innerHTML=`<div class="compare-diff-spacer" style="height:${safeStart*DIFF_ITEM_HEIGHT}px"></div>${html}<div class="compare-diff-spacer" style="height:${Math.max(0,(items.length-end)*DIFF_ITEM_HEIGHT)}px"></div>`;
    state.diffWindow={start:safeStart,end};
  }
  function renderDiffList(){
    state.diffList=visibleDiffs();
    const list=$('compare-diff-list');if(list)list.scrollTop=0;
    renderDiffWindow(0);
    $('compare-diff-counter').textContent='0 / 0';
  }
  function onDiffListScroll(){
    const list=$('compare-diff-list'),items=state.diffList||[];if(!list||!items.length)return;
    const start=Math.max(0,Math.floor(list.scrollTop/DIFF_ITEM_HEIGHT)-4);
    if(!state.diffWindow||start!==state.diffWindow.start)renderDiffWindow(start);
  }
  function scalePaneDimensions(root) {
    // Word projects absolute pt/px sizes on paragraphs AND runs. Shrink each
    // absolute display dimension once; inherited/em/% sizes retain their ratios.
    // Never change text, block IDs, table spans, or the downloaded source DOCX.
    const dimensions=['font-size','line-height','margin-left','margin-right','margin-top','margin-bottom','text-indent','padding-left','padding-right','padding-top','padding-bottom'];
    root.querySelectorAll('[style]').forEach(node=>dimensions.forEach(property=>{
      const value=node.style.getPropertyValue(property).trim(),match=value.match(/^(-?\d+(?:\.\d+)?)(pt|px)$/);
      if(match)node.style.setProperty(property,`${Number((Number(match[1])*.9).toFixed(3))}${match[2]}`);
    }));
  }
  function renderContract(pane, html) {
    pane.innerHTML=html||'';
    scalePaneDimensions(pane);
  }
  function markDiffTargets(pane) {
    if(!pane)return;
    pane.querySelectorAll('[data-diff-id]').forEach(mark=>{mark.tabIndex=0;mark.setAttribute('role','button');mark.setAttribute('aria-label','定位此处差异');});
  }
  function parseVirtualDocument(html) {
    if(!html||typeof DOMParser==='undefined')return {style:'',blocks:[]};
    const parsed=new DOMParser().parseFromString(html,'text/html');
    const wrapper=parsed.querySelector('.compare-document')||parsed.body;
    if(!wrapper)return {style:'',blocks:[]};
    const blocks=Array.from(wrapper.children).map(element=>{
      const tag=element.tagName.toLowerCase();
      const text=element.textContent||'';
      const heading=/^h[1-6]$/.test(tag)||element.classList.contains('compare-heading');
      return {html:element.outerHTML,blockId:element.getAttribute('data-block-id')||'',textLength:text.length,kind:tag==='table'?'table':heading?'heading':'paragraph'};
    });
    return {style:wrapper.getAttribute('style')||'',blocks};
  }
  class VirtualDocument {
    constructor(container,document,options={}) {
      this.container=container; this.blocks=document.blocks||[]; this.style=document.style||'';
      this.chunkSize=options.chunkSize||20; this.overscan=options.overscan||2;
      this.charsPerLine=options.charsPerLine||46; this.merged=Boolean(options.merged);
      this.onChange=options.onChange||null; this.chunks=[]; this.first=0; this.last=0; this.frame=null;
      this.blockIndex=new Map(); this.blocks.forEach((block,index)=>{if(block.blockId)this.blockIndex.set(block.blockId,index);});
      this.scrollHandler=()=>this.schedule();
      this.container.addEventListener('scroll',this.scrollHandler,{passive:true});
      this.build();
    }
    destroy(){this.container.removeEventListener('scroll',this.scrollHandler);this.container.replaceChildren();}
    estimate(block){
      if(block.kind==='table')return Math.max(80,Math.min(1400,Math.ceil(block.textLength/36)*22+40));
      const lines=Math.max(1,Math.ceil(block.textLength/Math.max(16,this.charsPerLine)));
      return block.kind==='heading'?Math.max(34,lines*28+16):Math.max(26,lines*24+18);
    }
    build(){
      this.chunks=[];
      for(let start=0;start<this.blocks.length;start+=this.chunkSize){
        const end=Math.min(this.blocks.length,start+this.chunkSize);let height=0;
        for(let i=start;i<end;i++)height+=this.estimate(this.blocks[i]);
        this.chunks.push({start,end,height,el:null});
      }
      this.container.replaceChildren();
      const wrapper=document.createElement('div');
      wrapper.className='compare-document compare-virtual-document'+(this.merged?' compare-merged-document':'');
      if(this.style)wrapper.setAttribute('style',this.style);
      this.wrapper=wrapper;
      this.top=document.createElement('div');this.top.className='compare-virtual-spacer';
      this.windowEl=document.createElement('div');this.windowEl.className='compare-virtual-window';
      this.bottom=document.createElement('div');this.bottom.className='compare-virtual-spacer';
      wrapper.append(this.top,this.windowEl,this.bottom);this.container.append(wrapper);
      if(!this.blocks.length){
        const empty=document.createElement('p');empty.className='compare-block compare-empty';empty.textContent='暂无可呈现内容。';this.windowEl.append(empty);return;
      }
      this.refresh(true);
    }
    totalBefore(index){let sum=0;for(let i=0;i<index;i++)sum+=this.chunks[i].height;return sum;}
    totalAfter(index){let sum=0;for(let i=index;i<this.chunks.length;i++)sum+=this.chunks[i].height;return sum;}
    schedule(){if(this.frame!==null)return;this.frame=requestAnimationFrame(()=>{this.frame=null;this.refresh(false);});}
    currentRange(scrollTop,viewHeight){
      const overscanPx=Math.max(240,viewHeight*.6);let first=0,top=0;
      while(first<this.chunks.length-1&&top+this.chunks[first].height<scrollTop-overscanPx){top+=this.chunks[first].height;first++;}
      let last=first,y=top;
      while(last<this.chunks.length&&y<scrollTop+viewHeight+overscanPx){y+=this.chunks[last].height;last++;}
      first=Math.max(0,first-this.overscan);last=Math.min(this.chunks.length,last+this.overscan);
      return [first,last];
    }
    anchor(){const scrollTop=this.container.scrollTop;let top=0;for(let i=0;i<this.chunks.length;i++){if(scrollTop<top+this.chunks[i].height||i===this.chunks.length-1)return {index:i,offset:scrollTop-top};top+=this.chunks[i].height;}return {index:0,offset:0};}
    refresh(force){
      if(!this.chunks.length)return;
      const [first,last]=this.currentRange(this.container.scrollTop,this.container.clientHeight||600);
      if(!force&&first===this.first&&last===this.last)return;
      const anchor=this.anchor(),anchorTop=this.totalBefore(anchor.index);
      this.first=first;this.last=last;
      for(let i=0;i<this.chunks.length;i++){const chunk=this.chunks[i];if((i<first||i>=last)&&chunk.el){chunk.el.remove();chunk.el=null;chunk.measured=false;}}
      for(let i=first;i<last;i++){
        const chunk=this.chunks[i];
        if(!chunk.el){
          const element=document.createElement('div');element.className='compare-virtual-chunk';
          if(chunk.html){element.innerHTML=chunk.html;}
          else{
            element.innerHTML=this.blocks.slice(chunk.start,chunk.end).map(block=>block.html).join('');
            scalePaneDimensions(element);markDiffTargets(element);chunk.html=element.innerHTML;
          }
          chunk.el=element;chunk.measured=false;
        }
      }
      this.windowEl.replaceChildren(...this.chunks.slice(first,last).map(chunk=>chunk.el).filter(Boolean));
      for(let i=first;i<last;i++){const chunk=this.chunks[i];if(!chunk.measured&&chunk.el){chunk.height=Math.max(1,chunk.el.getBoundingClientRect().height);chunk.measured=true;}}
      this.top.style.height=`${this.totalBefore(first)}px`;
      this.bottom.style.height=`${this.totalAfter(last)}px`;
      if(anchor.index>=first&&anchor.index<last){
        const nextTop=this.totalBefore(anchor.index);
        if(Math.abs(nextTop-anchorTop)>.5)this.container.scrollTop=nextTop+anchor.offset;
      }
      if(this.onChange)this.onChange();
    }
    resetMeasurements(){
      for(const chunk of this.chunks){chunk.measured=false;}
    }
    scrollToBlock(blockId){
      const index=this.blockIndex.get(blockId);if(index===undefined)return false;
      let chunkIndex=0;for(let i=0;i<this.chunks.length;i++){if(index<this.chunks[i].end){chunkIndex=i;break;}}
      this.container.scrollTop=Math.max(0,this.totalBefore(chunkIndex)-24);
      this.refresh(true);
      requestAnimationFrame(()=>this.refresh(true));
      return true;
    }
  }
  function virtualize(container, document, options={}){
    if(!container)return null;
    if(container._virtualDoc)container._virtualDoc.destroy();
    const instance=new VirtualDocument(container,document,options);
    container._virtualDoc=instance;
    return instance;
  }
  function refreshVirtualLayouts(){
    for(const id of ['compare-word-merged-pane','compare-word-left-pane','compare-word-right-pane','compare-left-pane','compare-right-pane']){
      const pane=$(id),instance=pane?._virtualDoc;
      if(instance&&pane.clientHeight){instance.resetMeasurements();instance.refresh(true);}
    }
  }

  function onVirtualChange(){
    refreshDiffMarks();markActiveDiff();
    if(state.viewMode==='classic'){state.diffPositions=null;drawLines();}
  }
  function clearVirtual(container){if(container?._virtualDoc){container._virtualDoc.destroy();container._virtualDoc=null;}}
  function ensureDoc(side){
    if(!state.docs)state.docs={};
    if(!state.docs[side])state.docs[side]=parseVirtualDocument(state.rawDocs?.[side]||'');
    return state.docs[side];
  }
  function renderWordSources() {
    if(!state.view||state.wordSourcesRendered||!state.docs)return;
    virtualize($('compare-word-left-pane'),ensureDoc('left'),{charsPerLine:30,onChange:onVirtualChange});
    virtualize($('compare-word-right-pane'),ensureDoc('right'),{charsPerLine:30,onChange:onVirtualChange});
    state.wordSourcesRendered=true;refreshDiffMarks();markActiveDiff();
  }
  function renderClassicView() {
    if(!state.view||state.classicRendered||!state.docs)return;
    virtualize($('compare-left-pane'),ensureDoc('left'),{charsPerLine:40,onChange:onVirtualChange});
    virtualize($('compare-right-pane'),ensureDoc('right'),{charsPerLine:40,onChange:onVirtualChange});
    state.classicRendered=true;state.diffPositions=null;refreshDiffMarks();markActiveDiff();
  }
  function setFullscreenViewer(open) {
    const viewer=$('compare-viewer'); if(!viewer)return;
    document.body.classList.toggle('compare-fullscreen-open', Boolean(open));
    viewer.hidden=!open;
    const backdrop=$('compare-viewer-backdrop'); if(backdrop)backdrop.hidden=!open;
    if(open)requestAnimationFrame(()=>viewer.focus?.());
  }
  function closeViewer() {
    setFullscreenViewer(false);
    document.querySelector('.compare-pair-status.is-selected')?.focus?.();
  }
  function renderViewer(payload) {
    state.view=payload; state.diffIndex=0; const d=payload.diffs||[]; setFullscreenViewer(true);
    const pairLabel=payload.pair?.label||'合同比对';
    $('compare-pair-title').textContent=pairLabel;
    const leftName=payload.left?.name||'合同A',rightName=payload.right?.name||'合同B';
    $('compare-left-name').textContent=leftName; $('compare-right-name').textContent=rightName;
    $('compare-classic-left-name').textContent=leftName; $('compare-classic-right-name').textContent=rightName;
    $('compare-merged-name').textContent=payload.merged?.name||rightName;
    $('compare-left-title').textContent=leftName; $('compare-right-title').textContent=rightName;
    $('compare-merged-title').textContent=pairLabel;
    const s=payload.summary||{};
    $('compare-summary').textContent=`共 ${s.total||0} 处差异 · 修改 ${s.modify||0} · 新增 ${s.insert||0} · 删除 ${s.delete||0}`;
    $('compare-revision-count').textContent=String(d.length);
    $('compare-revision-count-rail').textContent=String(d.length);
    const cov=payload.coverage||{}; const incomplete=cov.status!=='complete'; const warnings=cov.warnings||[];
    const chip=$('compare-coverage-chip'), chipSummary=$('compare-coverage-summary'), chipList=$('compare-coverage-list');
    if(chip&&chipSummary&&chipList){
      chip.hidden=!incomplete; chip.open=false;
      chipSummary.textContent=incomplete?`覆盖不完整 · ${warnings.length} 项未覆盖`:'';
      chipList.replaceChildren();
      if(incomplete){
        const intro=document.createElement('p'); intro.textContent='以下内容未纳入比较，请人工复核，不要据此确认全文无差异。'; chipList.append(intro);
        if(warnings.length){const ul=document.createElement('ul'); warnings.forEach(warning=>{const li=document.createElement('li');li.textContent=warning;ul.append(li);});chipList.append(ul);}
      }
    }
    state.classicRendered=false; state.wordSourcesRendered=false; state.diffPositions=null;
    state.rawDocs={left:payload.left?.html||'',right:payload.right?.html||''};
    state.docs={merged:parseVirtualDocument(payload.merged?.html||payload.right?.html)};
    virtualize($('compare-word-merged-pane'),state.docs.merged,{merged:true,charsPerLine:48,onChange:onVirtualChange});
    refreshDiffMarks(); $('compare-diff-counter').textContent='0 / 0'; renderDiffList();
    if(!d.length)$('compare-diff-list').innerHTML=`<p class="empty">${incomplete?'已覆盖范围内没有发现文字差异。':'两份合同没有文字差异。'}</p>`;
    setMobilePane('merged',false);
    drawLines();
    if(state.viewMode==='classic')renderClassicView();
    if(d.length)focusDiff(0);
    const layout=$('compare-word-layout');
    if(state.viewMode==='word'&&layout&&!layout.classList.contains('is-sources-hidden')){
      const schedule=window.requestIdleCallback?window.requestIdleCallback(()=>{if(state.view===payload)renderWordSources();},{timeout:600}):setTimeout(()=>{if(state.view===payload)renderWordSources();},60);
      void schedule;
    }
  }
  async function openPair(index,fromRoute=false) {
    const p=state.pairs[index];if(!p)return;
    if(!fromRoute&&state.view&&api.navigate&&api.route?.().pair!==p.id){api.navigate('compare',{mode:'detail',id:state.task.id,pair:p.id});return;}
    if(state.selectionDirty){selectionStatus('请先保存当前选择，再切换合同组。',true);return;}
    if(state.view?.pair?.id===p.id){state.pairIndex=index;state.selectedPairId=p.id;renderPairs();setFullscreenViewer(true);await loadSelection(p.id);return;}
    resetSelection();const token=++state.requestToken;
    state.pairIndex=index;state.selectedPairId=p.id;state.view=null;state.classicRendered=false;state.wordSourcesRendered=false;state.diffPositions=null;state.docs=null;state.rawDocs=null;state.mergedMarks=state.wordLeftMarks=state.wordRightMarks=state.leftMarks=state.rightMarks=null;renderPairs();
    setFullscreenViewer(false);$('compare-lines')?.replaceChildren();for(const pane of [$('compare-word-merged-pane'),$('compare-word-left-pane'),$('compare-word-right-pane'),$('compare-left-pane'),$('compare-right-pane')]){clearVirtual(pane);if(pane)pane.innerHTML='';}$('compare-pair-counter').textContent=`${index+1} / ${state.pairs.length}`;
    if(!['succeeded','incomplete'].includes(p.status))return;
    try {const payload=await json(`/api/compare/pairs/${encodeURIComponent(p.id)}/view`);if(token===state.requestToken){p.viewError='';renderPairs();renderViewer(payload);await loadSelection(p.id);}}
    catch(e){if(token===state.requestToken){p.viewError=`读取结果失败：${e.message}`;renderPairs();}}
  }
   async function openTask(id) {
     if(api.navigate&&(api.route?.().view!=='compare'||api.route?.().mode!=='detail'||api.route?.().id!==id)){api.navigate('compare',{mode:'detail',id});return;}
     clearTimeout(state.poll);const token=++state.requestToken;
     try{const task=await json(`/api/compare/tasks/${encodeURIComponent(id)}`);if(token!==state.requestToken)return;
       const previousPairId=api.route?.().pair||state.selectedPairId;renderTask(task);
       const kept=state.pairs.findIndex(p=>p.id===previousPairId),idx=kept>=0?kept:state.pairs.findIndex(p=>['succeeded','incomplete'].includes(p.status));
       if(idx>=0){if(state.selectedPairId===state.pairs[idx]?.id&&state.view){$('compare-viewer').hidden=false;$('compare-pair-counter').textContent=`${idx+1} / ${state.pairs.length}`;}else await openPair(idx,true);}else $('compare-viewer').hidden=true;
       if(['queued','running','uploading'].includes(state.task?.status))state.poll=setTimeout(()=>openTask(id),2500);
     }catch(e){if(token===state.requestToken){$('compare-detail').hidden=false;$('compare-task-status').textContent=`读取任务失败：${e.message}`;}}
   }
  function applyRoute(route){
    if(route.view!=='compare'){clearTimeout(state.poll);closeViewer();return;}
    const mode=['list','new','detail'].includes(route.mode)?route.mode:'list';$('view-compare').dataset.mode=mode;
    if(mode==='detail'&&state.task?.id!==route.id)$('compare-task-name').textContent='正在读取任务…';
    if(mode==='new'){if($('compare-create').hidden)showCreate(true);return;}
    $('compare-create').hidden=true;
    if(mode==='list'){$('compare-search').value=route.q||'';$('compare-list-filter').value=route.status||'';$('compare-detail').hidden=true;closeViewer();clearTimeout(state.poll);if(api.ready?.())loadTasks();return;}
    if(!api.ready?.())return;
    if(route.id)openTask(route.id);else{$('compare-task-status').textContent='请先从比对任务列表选择任务。';$('compare-detail').hidden=false;}
  }
  function bind() {
    let searchTimer=null;
    const filterList=()=>api.navigate('compare',{mode:'list',q:$('compare-search').value.trim(),status:$('compare-list-filter').value,page:'1'});
    $('compare-search').addEventListener('input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(filterList,300);});
    $('compare-list-filter').addEventListener('change',filterList);
    document.addEventListener('click',e=>{const page=e.target.closest('[data-compare-list-page]');if(page)api.navigate('compare',{...api.route(),mode:'list',page:page.dataset.compareListPage});});
    window.FundLexCompare={hasUnsavedChanges:()=>state.selectionDirty};
    document.addEventListener('fundlex:route',e=>applyRoute(e.detail));
    document.addEventListener('click',e=>{
      const choose=e.target.closest('[data-compare-choose]');if(choose){choose.closest('.compare-file-card').querySelector('input[type=file]').click();return;}
      const folder=e.target.closest('[data-compare-folder]');if(folder)$(`compare-${folder.dataset.compareFolder}-folder`).click();
    });
    document.addEventListener('change',e=>{
      const card=e.target.closest('.compare-file-card');if(!card||!e.target.matches('input[type=file]'))return;
      const name=e.target.files?.[0]?.name||'';card.classList.toggle('has-file',!!name);
      const label=card.querySelector('.compare-file-name');label.textContent=name||'尚未选择合同';label.title=name;
      card.querySelector('[data-compare-choose]').textContent=name?'更换文件':'选择文件';
    });
    document.addEventListener('fundlex:identity-reset',resetSelection);
    window.addEventListener('beforeunload',event=>{if(state.selectionDirty){event.preventDefault();event.returnValue='';}});
    $('compare-new')?.addEventListener('click',()=>api.navigate?api.navigate('compare',{mode:'new'}):showCreate(true)); $('compare-add-pair')?.addEventListener('click',()=>{const index=state.inputs.length;state.inputs.push({});$('compare-pair-inputs')?.insertAdjacentHTML('beforeend',pairRow({},index));syncInputIndexes();}); $('compare-submit')?.addEventListener('click',createTask); $('compare-refresh')?.addEventListener('click',loadTasks);
    $('compare-close-viewer')?.addEventListener('click',closeViewer);
    $('compare-viewer-backdrop')?.addEventListener('click',closeViewer);
    document.addEventListener('click',event=>{const chip=$('compare-coverage-chip');if(chip&&chip.open&&!event.target.closest('#compare-coverage-chip'))chip.open=false;});
    document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!$('compare-viewer').hidden){event.preventDefault();closeViewer();}});
    $('compare-prev-diff')?.addEventListener('click',()=>focusDiff(state.diffIndex-1)); $('compare-next-diff')?.addEventListener('click',()=>focusDiff(state.diffIndex+1)); $('compare-prev-pair')?.addEventListener('click',()=>openPair(Math.max(0,state.pairIndex-1))); $('compare-next-pair')?.addEventListener('click',()=>openPair(Math.min(state.pairs.length-1,state.pairIndex+1))); $('compare-report')?.addEventListener('click',()=>{if(!state.view)return;const blob=new Blob([JSON.stringify(state.view,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`${state.task?.name||'合同比对'}-差异报告.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}); $('compare-selection-left-all')?.addEventListener('click',()=>setAllSelections('left')); $('compare-selection-right-all')?.addEventListener('click',()=>setAllSelections('right')); $('compare-selection-pending')?.addEventListener('click',()=>{const index=visibleDiffs().findIndex(item=>selectionDecision(item.id)==='pending');if(index>=0)focusDiff(index);}); $('compare-selection-save')?.addEventListener('click',saveSelectionDraft); $('compare-selection-preview')?.addEventListener('click',previewSelection); $('compare-selection-generate')?.addEventListener('click',generateSelection); $('compare-active-only')?.addEventListener('change',drawLines); $('compare-diff-filter')?.addEventListener('change',()=>{state.diffIndex=0;renderDiffList();focusDiff(0);}); $('compare-retry')?.addEventListener('click',continueUploads); document.querySelectorAll('[data-word-pane]').forEach(btn=>btn.addEventListener('click',()=>setMobilePane(btn.dataset.wordPane))); $('compare-show-sources')?.addEventListener('change',e=>setSourcesVisible(e.target.checked)); $('compare-markup-mode')?.addEventListener('change',e=>setMarkupMode(e.target.value)); document.querySelectorAll('[data-compare-sources-close]').forEach(btn=>btn.addEventListener('click',()=>setSourcesVisible(false)));
      document.addEventListener('click',e=>{ const task=e.target.closest('[data-compare-task]');if(task){openTask(task.dataset.compareTask);return;}const pair=e.target.closest('[data-compare-pair]');if(pair){openPair(Number(pair.dataset.comparePair));return;}const download=e.target.closest('[data-selection-download]');if(download){downloadSelection(download.dataset.selectionDownload,download.dataset.selectionFilename);return;}const diff=e.target.closest('[data-compare-diff]');if(diff&&!e.target.closest('input')){focusDiff(visibleDiffs().findIndex(x=>x.id===diff.dataset.compareDiff));return;}const mark=e.target.closest('#compare-word-merged-pane [data-diff-id],#compare-word-left-pane [data-diff-id],#compare-word-right-pane [data-diff-id],#compare-left-pane [data-diff-id],#compare-right-pane [data-diff-id]');if(mark){focusDiff(visibleDiffs().findIndex(x=>x.id===mark.dataset.diffId));return;}const remove=e.target.closest('[data-compare-remove]');if(remove){const index=Number(remove.dataset.compareRemove),row=remove.closest('.compare-pair-input');state.inputs.splice(index,1);row?.remove();if(!state.inputs.length){state.inputs=[{}];renderInputs();}else syncInputIndexes();return;} });
     document.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.matches('#compare-word-merged-pane [data-diff-id],#compare-word-left-pane [data-diff-id],#compare-word-right-pane [data-diff-id],#compare-left-pane [data-diff-id],#compare-right-pane [data-diff-id]')){e.preventDefault();focusDiff(visibleDiffs().findIndex(x=>x.id===e.target.dataset.diffId));}});
      document.addEventListener('change',e=>{const choice=e.target.closest('[data-selection-choice]');if(choice){chooseSelection(choice.dataset.diffId,choice.value);return;}const row=e.target.closest('.compare-pair-input');if(row&&e.target.matches('input[type=file]')){const i=Number(row.dataset.pairIndex),entry=state.inputs[i]||(state.inputs[i]={});entry[e.target.matches('[data-compare-left]')?'_left':'_right']=e.target.files?.[0]||null;row.querySelector('.compare-file-label').textContent=[entry._left?.name,entry._right?.name].filter(Boolean).join(' / ')||'尚未选择文件';return;}if(e.target.id==='compare-left-folder'||e.target.id==='compare-right-folder'){const side=e.target.id.includes('left')?'left':'right';state[`folder${side[0].toUpperCase()+side.slice(1)}`]=[...e.target.files].filter(f=>fileName(f).toLowerCase().endsWith('.docx')).sort((a,b)=>relativePath(a).localeCompare(relativePath(b)));const other=side==='left'?state.folderRight:state.folderLeft;if(!other?.length)return;const left=state.folderLeft||[],right=state.folderRight||[],map=new Map(right.map(f=>[relativePath(f),f])),used=new Set(),entries=left.map(f=>{const r=map.get(relativePath(f));if(r)used.add(r);return {_left:f,_right:r||null};});for(const f of right)if(!used.has(f))entries.push({_left:null,_right:f});state.inputs=entries;renderInputs();$('compare-upload-message').textContent=`已按相对路径配对 ${entries.filter(x=>x._left&&x._right).length} 组；${entries.filter(x=>!x._left||!x._right).length} 个文件未配对，可手工补齐。`;}});
     bindCompareSplitter();
      for(const pane of allPanels())pane?.addEventListener('scroll',()=>syncPaneScroll(pane),{passive:true});
      window.addEventListener('resize',()=>{state.diffPositions=null;refreshVirtualLayouts();drawLines();});
      const body=$('compare-view-body'); if(body&&window.ResizeObserver)new ResizeObserver(drawLines).observe(body);
      document.querySelectorAll('[data-compare-view-mode]').forEach(button=>button.addEventListener('click',()=>setViewMode(button.dataset.compareViewMode)));
      document.querySelectorAll('#compare-classic-view [data-compare-side]').forEach(button=>button.addEventListener('click',()=>setClassicSide(button.dataset.compareSide)));
      try { const storedSources=localStorage.getItem('fundlex-compare-show-sources'); setSourcesVisible(storedSources==='1',false); const storedMarkup=localStorage.getItem('fundlex-compare-markup'); if(storedMarkup)setMarkupMode(storedMarkup,false); const storedPane=localStorage.getItem('fundlex-compare-mobile-pane'); if(storedPane)setMobilePane(storedPane,false); const storedMode=localStorage.getItem('fundlex-compare-view-mode'); if(storedMode)setViewMode(storedMode,false); const storedSide=localStorage.getItem('fundlex-compare-classic-side'); if(storedSide)setClassicSide(storedSide,false); } catch {}
      document.addEventListener('fundlex:view',e=>{if(e.detail==='compare'){drawLines();}}); document.addEventListener('fundlex:identity-reset',()=>{clearTimeout(state.poll);state.identityToken++;state.listToken++;state.tasks=[];state.task=null;state.pairs=[];state.selectedPairId=null;state.view=null;state.mergedMarks=state.wordLeftMarks=state.wordRightMarks=state.leftMarks=state.rightMarks=null;state.selection=null;state.selectionDraft=null;state.selectionDirty=false;state.uploadDraft=null;state.inputs=[{}];state.requestToken++;state.selectionToken++;resetFolders();$('compare-create').hidden=true;$('compare-submit').disabled=false;$('compare-retry').hidden=true;$('compare-upload-message').textContent='';$('compare-name').value='';$('compare-detail').hidden=true;setFullscreenViewer(false);for(const pane of [$('compare-word-merged-pane'),$('compare-word-left-pane'),$('compare-word-right-pane'),$('compare-left-pane'),$('compare-right-pane')]){clearVirtual(pane);if(pane)pane.innerHTML='';}$('compare-diff-list').innerHTML='';$('compare-selection-downloads').replaceChildren();selectionStatus('');$('compare-lines')?.replaceChildren();$('compare-diff-counter').textContent='0 / 0';$('compare-revision-count').textContent='0';$('compare-revision-count-rail').textContent='0';renderInputs();renderTasks();}); state.inputs=[{}];renderInputs();applyRoute(api.route?.()||{view:'compare',mode:'list'});
  }
  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded',bind); else bind();
})();
