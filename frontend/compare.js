(() => {
  'use strict';
  const api = window.FundLexWorkbench || {};
  const $ = id => document.getElementById(id);
  const esc = api.esc || (v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])));
  const state = { tasks: [], task: null, pairs: [], pairIndex: 0, selectedPairId: null, view: null, diffIndex: 0, poll: null, requestToken: 0, lineFrame: null, scrollFrame: null, scrollSource: null, identityToken: 0, listToken: 0, inputs: [{}], uploadDraft: null, selection: null, selectionBusy: false, selectionDirty: false, splitRatio: .5, pendingSplitRatio: .5, splitDragging: false, leftMarks: null, rightMarks: null };
  const SPLIT_KEY = 'fundlex-compare-split-ratio', SPLIT_GUTTER = 28;
  const clampSplitRatio = value => { const number = Number(value); return value !== null && value !== '' && Number.isFinite(number) ? Math.min(.8, Math.max(.2, number)) : .5; };
  function storedSplitRatio() { try { return clampSplitRatio(localStorage.getItem(SPLIT_KEY)); } catch { return .5; } }
  const json = (path, options) => api.json ? api.json(path, options) : fetch(path, options).then(async r => { if (!r.ok) throw Error(await r.text()); return r.json(); });
  const text = id => ($(id) || {}).textContent || '';
  const fileName = file => String(file?.name || '').replace(/\\/g, '/').split('/').pop();
  const relativePath = file => {
    const raw=String(file?.webkitRelativePath || '').replace(/\\/g, '/');
    if(raw) return raw.split('/').filter(Boolean).slice(1).join('/') || fileName(file);
    return fileName(file);
  };
  const legacyDoc = file => /\.doc$/i.test(fileName(file));
  const legacyDocMessage = files => `检测到 Word 97-2003 格式（.doc）文件：${files.map(fileName).join('、')}。请用 Word/WPS 打开后“另存为” .docx，再重新选择。`;
  function pairRow(pair = {}, index) {
    const selected = [pair.left?.name || fileName(pair._left), pair.right?.name || fileName(pair._right)].filter(Boolean).join(' / ');
    return `<div class="compare-pair-input" data-pair-index="${index}"><div class="compare-pair-head"><strong>第 ${index + 1} 组</strong><button type="button" class="btn-link" data-compare-remove="${index}" ${index ? '' : 'disabled'}>移除</button></div><div class="compare-side-inputs"><label><span>原版（基准）</span><input type="file" accept=".doc,.docx,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document" data-compare-left="${index}"></label><label><span>对比版（修订）</span><input type="file" accept=".doc,.docx,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document" data-compare-right="${index}"></label></div><p class="subnote compare-file-label" data-compare-label="${index}">${esc(selected||'尚未选择文件')}</p></div>`;
  }
  function renderInputs() { const box=$('compare-pair-inputs'); if (box) box.innerHTML = (state.inputs || [{}]).map(pairRow).join(''); }
  function syncInputIndexes() { document.querySelectorAll('#compare-pair-inputs .compare-pair-input').forEach((row,i)=>{ row.dataset.pairIndex=String(i); row.querySelector('[data-compare-left]')?.setAttribute('data-compare-left',String(i)); row.querySelector('[data-compare-right]')?.setAttribute('data-compare-right',String(i)); row.querySelector('[data-compare-remove]')?.setAttribute('data-compare-remove',String(i)); }); }
  function selectedFiles() { return (state.inputs || []).map(x => ({ left: x._left || x.left, right: x._right || x.right })).filter(x => x.left || x.right); }
  function resetFolders() { state.folderLeft=[]; state.folderRight=[]; for(const id of ['compare-left-folder','compare-right-folder'])if($(id))$(id).value=''; }
  function showCreate(show=true) { $('compare-create').hidden = !show; if (show) { clearTimeout(state.poll); state.requestToken++; $('compare-detail').hidden=true; $('compare-viewer').hidden=true; state.view=null; state.leftMarks=state.rightMarks=null; state.uploadDraft=null; state.inputs=[{}]; resetFolders(); $('compare-upload-message').textContent=''; $('compare-retry').hidden=true; $('compare-lines').replaceChildren(); renderInputs(); } }
  function statusLabel(v) { return ({pending:'待上传',queued:'排队中',leased:'处理中',running:'处理中',succeeded:'已完成',incomplete:'覆盖不完整',failed:'失败',retry_wait:'等待重试',sealed:'已提交',uploading:'上传中',completed:'已处理'}[v] || v || '—'); }
  function uploadErrorLabel(code) { return code === 'LEGACY_DOC_UNSUPPORTED' ? '请将 .doc 另存为 .docx' : code; }
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
    $('compare-pair-list').innerHTML=`<div class="compare-pair-statuses">${state.pairs.map((p,i)=>`<button type="button" class="compare-pair-status ${p.id===state.selectedPairId?'is-selected':''} ${['succeeded','incomplete'].includes(p.status)?'is-done':''} ${p.status==='incomplete'?'is-incomplete':''} ${p.status==='failed'||p.viewError?'is-failed':''}" data-compare-pair="${i}"><span class="compare-pair-number">${String(i+1).padStart(2,'0')}</span><span class="compare-pair-main"><strong>${esc(p.label||`第 ${i+1} 组`)}</strong><small>${esc(p.left?.name||'原版未命名')} → ${esc(p.right?.name||'对比版未命名')}</small></span><span class="compare-pair-state">${esc(statusLabel(p.status))}${p.summary?` · ${p.summary.total} 处`:''}</span>${p.error_code||p.viewError?`<span class="compare-pair-error" role="status">${esc(p.viewError||`处理失败：${uploadErrorLabel(p.error_code)}`)}</span>`:''}</button>`).join('')}</div>`;
  }
  function markFiles(form, files, pair) { const ids=[]; for (const side of ['left','right']) { form.append('files',files[side],pair[side].name); ids.push(pair[side].client_id); } form.append('client_ids', JSON.stringify(ids)); }
  async function continueUploads() {
    const draft=state.uploadDraft, message=$('compare-upload-message'); if(!draft)return;
    const identity=state.identityToken; $('compare-submit').disabled=true; $('compare-retry').hidden=true;
    try {
      let acceptedRevisionTotal=0;
      for (let i=draft.next;i<draft.files.length;i++) {
        const x=draft.files[i]; message.textContent=`正在上传第 ${i+1} / ${draft.files.length} 组…`;
        const form=new FormData(); markFiles(form,x,draft.pairs[i]); const uploaded=await json(`/api/compare/tasks/${encodeURIComponent(draft.task.id)}/uploads`,{method:'POST',body:form});
        if(identity!==state.identityToken)return; const receipts=uploaded.receipts||[],bad=['left','right'].map(side=>receipts.find(r=>r.client_id===draft.pairs[i][side].client_id)).filter(r=>!r||!['accepted','already_accepted'].includes(r.status));
        if(bad.length)throw Error(`第 ${i+1} 组上传未完成：${bad.map(r=>r?`${r.client_id}（${uploadErrorLabel(r.error_code)||r.status}）`:'缺少上传回执').join('、')}`);
        acceptedRevisionTotal+=receipts.reduce((sum,r)=>sum+Number(r?.revisions_accepted||0),0);
        draft.next=i+1;
      }
      message.textContent=acceptedRevisionTotal?`已自动接受 ${acceptedRevisionTotal} 处已有修订，正在提交对比任务…`:'文件已上传，正在提交对比任务…'; await json(`/api/compare/tasks/${encodeURIComponent(draft.task.id)}/seal`,{method:'POST'}); if(identity!==state.identityToken)return;
      message.textContent=acceptedRevisionTotal?`已提交，对比任务正在处理；已自动接受 ${acceptedRevisionTotal} 处已有修订。`:'已提交，对比任务正在处理。'; state.uploadDraft=null; showCreate(false); if(acceptedRevisionTotal)api.toast?.(`已自动接受 ${acceptedRevisionTotal} 处已有修订，任务已进入对比。`); await loadTasks(); await openTask(draft.task.id);
    } catch(e) { if(identity===state.identityToken){message.textContent=`上传中断：${e.message}。已完成的文件已保留，可点击“继续上传”。`; $('compare-retry').hidden=false;} }
    finally { if(identity===state.identityToken)$('compare-submit').disabled=false; }
  }
  async function createTask() {
    const files=selectedFiles(), message=$('compare-upload-message');
    const legacy=files.flatMap(x=>[x.left,x.right]).filter(f=>f&&legacyDoc(f));
    if (legacy.length) { message.textContent=legacyDocMessage(legacy); return; }
    if (!files.length || files.some(x=>!x.left||!x.right)) { message.textContent='每组都需要同时选择原版和对比版 DOCX。'; return; }
    const identity=state.identityToken; const name=($('compare-name').value||'合同对比').trim(); const pairs=files.map((x,i)=>{const leftId=`L${i}-${crypto.randomUUID()}`,rightId=`R${i}-${crypto.randomUUID()}`;return {client_pair_id:`P${i+1}`,label:`合同 ${i+1}`,left:{client_id:leftId,name:fileName(x.left),size:x.left.size},right:{client_id:rightId,name:fileName(x.right),size:x.right.size}};});
    const key=`compare-${Date.now()}-${crypto.randomUUID()}`; message.textContent='正在创建对比任务…'; $('compare-submit').disabled=true;
    try { const task=await json('/api/compare/tasks',{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':key},body:JSON.stringify({name,pairs})}); if(identity!==state.identityToken)return; state.uploadDraft={task,pairs,files,next:0}; await continueUploads(); }
    catch(e) { if(identity===state.identityToken){message.textContent=`创建任务失败：${e.message}`;$('compare-submit').disabled=false;} }
  }
  function blockFor(side, id) { return document.querySelector(`#compare-${side}-pane [data-block-id="${CSS.escape(id)}"]`); }
  function targetFor(side, span, item) { const pane=$(`compare-${side}-pane`); if(!pane)return null; const id=span?.block_id || item?.[`${side}_anchor`]?.block_id; return id ? blockFor(side,id) : pane.querySelector('.compare-block'); }
  function applySplitRatio(value, persist = true) {
    const ratio = clampSplitRatio(value), cols=$('compare-columns'), head=$('compare-columns-head'), gutter=$('compare-gutter');
    if (!cols) return;
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
      applySplitRatio(apply ? state.pendingSplitRatio : state.splitRatio, true); drawLines();
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
    const left=$('compare-left-pane'),right=$('compare-right-pane');
    state.leftMarks=left?new Map([...left.querySelectorAll('[data-diff-id]')].map(n=>[n.dataset.diffId,n])):null;
    state.rightMarks=right?new Map([...right.querySelectorAll('[data-diff-id]')].map(n=>[n.dataset.diffId,n])):null;
  }
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
      if(!state.leftMarks||!state.rightMarks)refreshDiffMarks();
      const leftMarks=state.leftMarks,rightMarks=state.rightMarks;
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
  function visibleDiffs() { const all=state.view?.diffs||[], filter=$('compare-diff-filter')?.value||''; return filter?all.filter(x=>x.type===filter):all; }
  function currentSelection() { return state.selection && state.selection.pair_id ? state.selection : null; }
  function decisionMap() { const sel = currentSelection(); if (!sel) return {}; if (!sel.decisions || typeof sel.decisions !== 'object') sel.decisions = {}; return sel.decisions; }
  function selectionCounts() { const diffs = state.view?.diffs || [], map = decisionMap(); let left = 0, right = 0, pending = 0; for (const item of diffs) { const value = map[item.id] || 'pending'; if (value === 'left') left++; else if (value === 'right') right++; else pending++; } return { total: diffs.length, left, right, pending }; }
  function setSelectionStatus(message, kind) { const box = $('compare-selection-status'); if (!box) return; box.textContent = message; box.className = `compare-selection-status${kind ? ` is-${kind}` : ''}`; }
  function renderSelectionVersions() {
    const box = $('compare-selection-versions'); if (!box) return;
    const versions = state.selection?.artifacts || [];
    if (!versions.length) { box.hidden = true; box.innerHTML = ''; return; }
    box.hidden = false;
    box.innerHTML = versions.map(version => {
      const stateText = version.current ? '当前版本' : version.stale ? '已过期' : '历史版本';
      const files = ['final', 'redline'].map(kind => {
        const file = (version.files || {})[kind]; if (!file) return '';
        return `<button type="button" class="btn btn-sm" data-compare-download="${esc(file.download_url)}" data-compare-filename="选择版-${kind === 'final' ? '最终版' : '修订版'}-v${version.version}.docx">下载${kind === 'final' ? '最终版' : '修订版'}</button>`;
      }).join(' ');
      const report = version.report ? `<button type="button" class="btn btn-sm" data-compare-report-version="${version.version}">下载选择报告</button>` : '';
      return `<div class="compare-selection-version"><strong>版本 ${version.version}</strong><span class="${version.current ? 'is-current' : version.stale ? 'is-stale' : ''}">${stateText}</span><span>决策 ${esc(String(version.decision_hash || '').slice(0, 12))}…</span>${files} ${report}</div>`;
    }).join('');
  }
  function renderSelection() {
    const sel = currentSelection(), box = $('compare-selection'); if (!box) return;
    const counts = selectionCounts(), allChosen = !!sel && counts.pending === 0;
    $('compare-selection-progress').textContent = `已选 ${counts.left + counts.right} / ${counts.total} 处 · 原版 ${counts.left} · 对比版 ${counts.right} · 待选 ${counts.pending}`;
    for (const id of ['compare-select-left', 'compare-select-right', 'compare-selection-clear']) if ($(id)) $(id).disabled = !sel || state.selectionBusy;
    if ($('compare-selection-save')) $('compare-selection-save').disabled = !sel || state.selectionBusy || !state.selectionDirty;
    if ($('compare-selection-preview')) $('compare-selection-preview').disabled = !sel || state.selectionBusy;
    if ($('compare-selection-generate')) $('compare-selection-generate').disabled = !allChosen || state.selectionBusy;
    renderSelectionVersions();
  }
  function setAllDecisions(value) {
    const sel = currentSelection(); if (!sel || !state.view) return;
    const map = decisionMap(), diffs = state.view.diffs || [];
    for (const item of diffs) map[item.id] = value;
    state.selectionDirty = true; renderDiffList(); renderSelection();
    setSelectionStatus(`已将全部 ${diffs.length} 处差异设为${value === 'left' ? '原版' : '对比版'}；保存后生效。筛选不会改变未显示项。`);
  }
  async function refreshSelection() {
    const sel = currentSelection(); if (!sel) return null;
    try {
      const next = await json(`/api/compare/pairs/${encodeURIComponent(sel.pair_id)}/selection`);
      state.selection = next; state.selectionDirty = false; renderDiffList(); renderSelection(); return next;
    } catch (error) { setSelectionStatus(`读取选择状态失败：${error.message}`, 'error'); return null; }
  }
  async function saveSelection(options = {}) {
    const sel = currentSelection(); if (!sel) return null;
    const token = state.requestToken; state.selectionBusy = true; renderSelection();
    try {
      const payload = await json(`/api/compare/pairs/${encodeURIComponent(sel.pair_id)}/selection`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ expected_epoch: sel.selection_epoch, result_sha256: sel.result_sha256, left_source_sha256: sel.left_source_sha256, right_source_sha256: sel.right_source_sha256, decisions: decisionMap() })
      });
      if (token !== state.requestToken) return null;
      state.selection = payload; state.selectionDirty = false; renderDiffList(); renderSelection();
      if (!options.silent) setSelectionStatus('选择已保存。', 'ok');
      return payload;
    } catch (error) {
      if (token === state.requestToken) {
        state.selectionDirty = true;
        if (error.raw === 'SELECTION_EPOCH_CONFLICT') { await refreshSelection(); setSelectionStatus('选择版本已变化，已重新读取当前草稿，请确认后重试。', 'error'); }
        else setSelectionStatus(`保存失败：${error.message}。本地选择仍保留，请重试。`, 'error');
      }
      return null;
    } finally { if (token === state.requestToken) { state.selectionBusy = false; renderSelection(); } }
  }
  async function previewSelection() {
    const sel = currentSelection(); if (!sel) return;
    state.selectionBusy = true; renderSelection();
    try {
      const payload = await json(`/api/compare/pairs/${encodeURIComponent(sel.pair_id)}/selection/preview`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decisions: decisionMap() })
      });
      const assessment = payload.assessment || {}, blocking = (assessment.issues || []).filter(item => item.blocking), pending = assessment.pending_ids || [];
      if (blocking.length) setSelectionStatus(`预览发现 ${blocking.length} 个结构阻塞：${blocking.map(item => item.code).join('、')}`, 'error');
      else if (pending.length) setSelectionStatus(`还有 ${pending.length} 处待选择，不能生成。`, 'error');
      else setSelectionStatus(`预览通过：将采用原版 ${assessment.counts?.left || 0} 处、对比版 ${assessment.counts?.right || 0} 处。`, 'ok');
    } catch (error) { setSelectionStatus(`预览失败：${error.message}`, 'error'); }
    finally { state.selectionBusy = false; renderSelection(); }
  }
  async function generateSelection() {
    let sel = currentSelection(); if (!sel) return;
    if (state.selectionDirty) { sel = await saveSelection({ silent: true }); if (!sel) return; }
    if (!sel.draft) { setSelectionStatus('请先保存选择，再生成选择版。', 'error'); return; }
    state.selectionBusy = true; renderSelection();
    try {
      const payload = await json(`/api/compare/pairs/${encodeURIComponent(sel.pair_id)}/selection/generate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ expected_epoch: sel.selection_epoch, decision_hash: sel.draft.decision_hash, result_sha256: sel.result_sha256 })
      });
      state.selection = await json(`/api/compare/pairs/${encodeURIComponent(sel.pair_id)}/selection`);
      setSelectionStatus(`已生成版本 ${payload.version}：最终版与修订痕迹版已保存，可下载核对。`, 'ok');
    } catch (error) {
      if (error.raw === 'SELECTION_EPOCH_CONFLICT' || error.raw === 'SELECTION_DECISION_CONFLICT') { await refreshSelection(); setSelectionStatus('选择版本已变化，已重新读取当前草稿，请确认后重试。', 'error'); }
      else setSelectionStatus(`生成失败：${error.message}`, 'error');
    } finally { state.selectionBusy = false; renderSelection(); }
  }
  function focusDiff(index) { const ds=visibleDiffs(); if(!ds.length){ $('compare-diff-counter').textContent='0 / 0'; return; } state.diffIndex=(index+ds.length)%ds.length; const id=ds[state.diffIndex].id; document.querySelectorAll('.compare-diff.is-active,.compare-diff-item.is-active').forEach(n=>n.classList.remove('is-active')); document.querySelectorAll(`[data-diff-id="${CSS.escape(id)}"]`).forEach(n=>n.classList.add('is-active')); document.querySelector(`[data-compare-diff="${CSS.escape(id)}"]`)?.classList.add('is-active'); $('compare-diff-counter').textContent=`${state.diffIndex+1} / ${ds.length}`; for(const side of ['left','right']) { const pane=$(`compare-${side}-pane`), target=pane?.querySelector(`[data-diff-id="${CSS.escape(id)}"]`); if(pane&&target){const pr=pane.getBoundingClientRect(),tr=target.getBoundingClientRect(); pane.scrollTo({top:pane.scrollTop+(tr.top+tr.height/2)-(pr.top+pr.height/2),behavior:'smooth'});}} requestAnimationFrame(drawLines); }
  function renderDiffList() {
    const d = visibleDiffs(), map = decisionMap();
    if (!d.length) { $('compare-diff-list').innerHTML = '<p class="empty">当前筛选条件下没有差异。</p>'; return; }
    $('compare-diff-list').innerHTML = d.map((x, i) => {
      const current = map[x.id] || 'pending';
      const choice = (value, label) => `<label class="${current === value ? 'is-selected' : ''}"><input type="radio" name="compare-selection-${esc(x.id)}" value="${value}" data-compare-choice="${esc(x.id)}" ${current === value ? 'checked' : ''}> ${label}</label>`;
      return `<div class="compare-diff-row"><button type="button" class="compare-diff-item" data-compare-diff="${esc(x.id)}"><span>${i + 1}</span><strong>${esc(x.type === 'modify' ? '修改' : x.type === 'insert' ? '新增' : '删除')}</strong><span>${esc(x.section || '正文')} · ${esc(x.left?.text || '')} ${x.right?.text ? '→ ' + esc(x.right.text) : ''}</span></button><div class="compare-diff-choice" role="radiogroup" aria-label="第 ${i + 1} 处差异选择">${choice('left', '采用原版')}${choice('right', '采用对比版')}</div></div>`;
    }).join('');
  }
  function renderViewer(payload) {
    state.view=payload; state.diffIndex=0; const d=payload.diffs||[]; $('compare-viewer').hidden=false; $('compare-pair-title').textContent=payload.pair?.label||'合同对比'; $('compare-left-name').textContent=payload.left?.name||'原版合同'; $('compare-right-name').textContent=payload.right?.name||'对比版合同'; const s=payload.summary||{}; $('compare-summary').textContent=`共 ${s.total||0} 处差异 · 修改 ${s.modify||0} · 新增 ${s.insert||0} · 删除 ${s.delete||0}`; const cov=payload.coverage||{}; const incomplete=cov.status!=='complete'; $('compare-coverage').hidden=!incomplete; $('compare-coverage').className=incomplete?'is-incomplete':''; $('compare-coverage').textContent=incomplete?`覆盖不完整：以下内容未纳入比较。请人工复核，不要据此确认全文无差异。${(cov.warnings||[]).length?' 未覆盖：'+cov.warnings.join('、'):''}`:'覆盖完整'; $('compare-left-pane').innerHTML=payload.left.html||''; $('compare-right-pane').innerHTML=payload.right.html||''; document.querySelectorAll('#compare-left-pane [data-diff-id],#compare-right-pane [data-diff-id]').forEach(mark=>{mark.tabIndex=0;mark.setAttribute('role','button');mark.setAttribute('aria-label','定位此处差异');}); refreshDiffMarks(); $('compare-diff-counter').textContent='0 / 0'; renderDiffList(); renderSelection(); if(!d.length)$('compare-diff-list').innerHTML=`<p class="empty">${incomplete?'已覆盖范围内没有发现文字差异，无法确认全文无差异。':'两份合同没有文字差异。'}</p>`; drawLines();if(d.length)focusDiff(0); }
    async function openPair(index) { const p=state.pairs[index]; if(!p)return; const token=++state.requestToken; state.pairIndex=index; state.selectedPairId=p.id; state.view=null; state.leftMarks=state.rightMarks=null; state.selection=null; state.selectionDirty=false; state.selectionBusy=false; renderPairs(); $('compare-viewer').hidden=true; $('compare-lines').replaceChildren(); $('compare-pair-counter').textContent=`${index+1} / ${state.pairs.length}`; if(!['succeeded','incomplete'].includes(p.status))return; setSelectionStatus('正在读取选择状态…'); try { const [payload,selection]=await Promise.all([json(`/api/compare/pairs/${encodeURIComponent(p.id)}/view`),json(`/api/compare/pairs/${encodeURIComponent(p.id)}/selection`).catch(error=>{if(token===state.requestToken)setSelectionStatus(`选择状态读取失败：${error.message}`,'error');return null;})]); if(token===state.requestToken){p.viewError='';if(selection)state.selection=selection;renderPairs();renderViewer(payload);if(selection)setSelectionStatus(selection.artifacts?.length?'已恢复最近保存的选择与生成版本。':'每处差异需要明确选择原版或对比版；未选择不能生成。');} } catch(e) { if(token===state.requestToken){p.viewError=`读取结果失败：${e.message}`;renderPairs();} } }
   async function openTask(id) { clearTimeout(state.poll); const token=++state.requestToken; try { const task=await json(`/api/compare/tasks/${encodeURIComponent(id)}`); if(token!==state.requestToken)return; const previousPairId=state.selectedPairId; renderTask(task); const kept=state.pairs.findIndex(p=>p.id===previousPairId); const idx=kept>=0?kept:state.pairs.findIndex(p=>['succeeded','incomplete'].includes(p.status)); if(idx>=0){ if(previousPairId===state.pairs[idx]?.id&&state.view) { $('compare-pair-counter').textContent=`${idx+1} / ${state.pairs.length}`; } else await openPair(idx); } else $('compare-viewer').hidden=true; if (['queued','running','uploading'].includes(state.task?.status)) { state.poll=setTimeout(()=>openTask(id),2500); } } catch(e) { if(token===state.requestToken)$('compare-task-status').textContent=`读取任务失败：${e.message}`; } }
  function bind() {
    $('compare-new')?.addEventListener('click',()=>showCreate(true)); $('compare-add-pair')?.addEventListener('click',()=>{const index=state.inputs.length;state.inputs.push({});$('compare-pair-inputs')?.insertAdjacentHTML('beforeend',pairRow({},index));syncInputIndexes();}); $('compare-submit')?.addEventListener('click',createTask); $('compare-refresh')?.addEventListener('click',loadTasks);
    $('compare-prev-diff')?.addEventListener('click',()=>focusDiff(state.diffIndex-1)); $('compare-next-diff')?.addEventListener('click',()=>focusDiff(state.diffIndex+1)); $('compare-prev-pair')?.addEventListener('click',()=>openPair(Math.max(0,state.pairIndex-1))); $('compare-next-pair')?.addEventListener('click',()=>openPair(Math.min(state.pairs.length-1,state.pairIndex+1))); $('compare-report')?.addEventListener('click',()=>{if(!state.view)return;const blob=new Blob([JSON.stringify(state.view,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`${state.task?.name||'合同对比'}-差异报告.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}); $('compare-active-only')?.addEventListener('change',drawLines); $('compare-diff-filter')?.addEventListener('change',()=>{state.diffIndex=0;renderDiffList();focusDiff(0);}); $('compare-retry')?.addEventListener('click',continueUploads); $('compare-select-left')?.addEventListener('click',()=>setAllDecisions('left')); $('compare-select-right')?.addEventListener('click',()=>setAllDecisions('right')); $('compare-selection-clear')?.addEventListener('click',()=>{const sel=currentSelection();if(!sel)return;const map=decisionMap();for(const item of (state.view?.diffs||[]))map[item.id]='pending';state.selectionDirty=true;renderDiffList();renderSelection();setSelectionStatus('已清除全部选择；保存后生效。');}); $('compare-selection-save')?.addEventListener('click',()=>saveSelection()); $('compare-selection-preview')?.addEventListener('click',previewSelection); $('compare-selection-generate')?.addEventListener('click',generateSelection); document.querySelectorAll('[data-compare-side]').forEach(btn=>btn.addEventListener('click',()=>{document.querySelectorAll('[data-compare-side]').forEach(x=>x.classList.toggle('is-active',x===btn));$('compare-viewer').dataset.mobileSide=btn.dataset.compareSide;}));
     document.addEventListener('click',e=>{ const report=e.target.closest('[data-compare-report-version]');if(report){const version=(state.selection?.artifacts||[]).find(item=>String(item.version)===report.dataset.compareReportVersion);if(!version?.report)return;const blob=new Blob([JSON.stringify(version.report,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`合同对比-选择报告-v${version.version}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);return;}const download=e.target.closest('[data-compare-download]');if(download){if(api.download)api.download(download.dataset.compareDownload,download.dataset.compareFilename||'选择版.docx');else api.toast?.('下载暂不可用，请刷新页面后重试。');return;}const task=e.target.closest('[data-compare-task]');if(task){openTask(task.dataset.compareTask);return;}const pair=e.target.closest('[data-compare-pair]');if(pair){openPair(Number(pair.dataset.comparePair));return;}const diff=e.target.closest('[data-compare-diff]');if(diff){focusDiff(visibleDiffs().findIndex(x=>x.id===diff.dataset.compareDiff));return;}const mark=e.target.closest('#compare-left-pane [data-diff-id],#compare-right-pane [data-diff-id]');if(mark){focusDiff(visibleDiffs().findIndex(x=>x.id===mark.dataset.diffId));return;}const remove=e.target.closest('[data-compare-remove]');if(remove){const index=Number(remove.dataset.compareRemove),row=remove.closest('.compare-pair-input');state.inputs.splice(index,1);row?.remove();if(!state.inputs.length){state.inputs=[{}];renderInputs();}else syncInputIndexes();return;} });
     document.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.matches('#compare-left-pane [data-diff-id],#compare-right-pane [data-diff-id]')){e.preventDefault();focusDiff(visibleDiffs().findIndex(x=>x.id===e.target.dataset.diffId));}});
    document.addEventListener('change',e=>{const choice=e.target.closest('[data-compare-choice]');if(choice){const sel=currentSelection();if(sel&&choice.checked){decisionMap()[choice.dataset.compareChoice]=choice.value;state.selectionDirty=true;const group=choice.closest('.compare-diff-choice');group?.querySelectorAll('label').forEach(label=>label.classList.toggle('is-selected',label.contains(choice)));renderSelection();setSelectionStatus('选择已修改，保存后生效。');}return;}const row=e.target.closest('.compare-pair-input');if(row&&e.target.matches('input[type=file]')){const i=Number(row.dataset.pairIndex),entry=state.inputs[i]||(state.inputs[i]={}),file=e.target.files?.[0]||null;entry[e.target.matches('[data-compare-left]')?'_left':'_right']=file;row.querySelector('.compare-file-label').textContent=[entry._left?.name,entry._right?.name].filter(Boolean).join(' / ')||'尚未选择文件';if(file&&legacyDoc(file))$('compare-upload-message').textContent=legacyDocMessage([file]);return;}if(e.target.id==='compare-left-folder'||e.target.id==='compare-right-folder'){const side=e.target.id.includes('left')?'left':'right';const allFiles=[...e.target.files],legacyFiles=allFiles.filter(f=>legacyDoc(f)),legacyNote=legacyFiles.length?`已忽略 ${legacyFiles.length} 个 Word 97-2003 格式（.doc）文件，请另存为 .docx 后重新选择。 `:'';state[`folder${side[0].toUpperCase()+side.slice(1)}`]=allFiles.filter(f=>/\.docx$/i.test(fileName(f))).sort((a,b)=>relativePath(a).localeCompare(relativePath(b)));const other=side==='left'?state.folderRight:state.folderLeft;if(!other?.length){if(legacyNote)$('compare-upload-message').textContent=legacyNote;return;}const left=state.folderLeft||[],right=state.folderRight||[],map=new Map(right.map(f=>[relativePath(f),f])),used=new Set(),entries=left.map(f=>{const r=map.get(relativePath(f));if(r)used.add(r);return {_left:f,_right:r||null};});for(const f of right)if(!used.has(f))entries.push({_left:null,_right:f});state.inputs=entries;renderInputs();$('compare-upload-message').textContent=`${legacyNote}已按相对路径配对 ${entries.filter(x=>x._left&&x._right).length} 组；${entries.filter(x=>!x._left||!x._right).length} 个文件未配对，可手工补齐。`;}});
     bindCompareSplitter();
     const cols=$('compare-columns'); if(cols){ for(const pane of [$('compare-left-pane'),$('compare-right-pane')])pane?.addEventListener('scroll',()=>syncPaneScroll(pane),{passive:true}); window.addEventListener('resize',()=>{applySplitRatio(state.splitRatio,false);drawLines();}); if(window.ResizeObserver)new ResizeObserver(drawLines).observe(cols); }
     document.addEventListener('fundlex:view',e=>{if(e.detail==='compare'){applySplitRatio(state.splitRatio,false);loadTasks();drawLines();}}); document.addEventListener('fundlex:identity-reset',()=>{clearTimeout(state.poll);state.identityToken++;state.listToken++;state.tasks=[];state.task=null;state.pairs=[];state.selectedPairId=null;state.view=null;state.leftMarks=state.rightMarks=null;state.uploadDraft=null;state.inputs=[{}];state.requestToken++;state.selection=null;state.selectionBusy=false;state.selectionDirty=false;resetFolders();$('compare-create').hidden=true;$('compare-submit').disabled=false;$('compare-retry').hidden=true;$('compare-upload-message').textContent='';$('compare-name').value='';$('compare-detail').hidden=true;$('compare-viewer').hidden=true;$('compare-left-pane').innerHTML='';$('compare-right-pane').innerHTML='';$('compare-diff-list').innerHTML='';$('compare-lines').replaceChildren();$('compare-diff-counter').textContent='0 / 0';$('compare-selection-versions').hidden=true;$('compare-selection-versions').innerHTML='';renderInputs();renderTasks();}); state.inputs=[{}];renderInputs(); const initialTask=new URLSearchParams(location.search).get('task'); loadTasks().then(()=>{if(initialTask)openTask(initialTask);});
  }
  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded',bind); else bind();
})();
