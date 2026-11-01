(() => {
  'use strict';
  const api = window.FundLexWorkbench || {};
  const $ = id => document.getElementById(id);
  const esc = api.esc || (v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])));
  const state = { tasks: [], task: null, pairs: [], pairIndex: 0, selectedPairId: null, view: null, selection: null, selectionDraft: null, selectionDirty: false, selectionSaving: false, selectionToken: 0, selectionSaveToken: 0, poll: null, pollTaskId: null, requestToken: 0, lineFrame: null, scrollFrame: null, scrollSource: null, syncTargets: new Set(), syncSettle: null, identityToken: 0, listToken: 0, inputs: [{}], uploadDraft: null, splitRatio: .5, pendingSplitRatio: .5, splitDragging: false, splitAlignTimer: null, splitRefreshTimer: null, lineSettle: null, linesScrolling: false, leftMarks: null, rightMarks: null, mergedMarks: null, wordLeftMarks: null, wordRightMarks: null, viewMode: 'word', classicSide: 'left', classicRendered: false, wordSourcesRendered: false, diffPositions: null, docs: null, rawDocs: null, alignment: null };
  const SPLIT_KEY = 'fundlex-compare-split-ratio', SPLIT_GUTTER = 28;
  const clampSplitRatio = value => { const number = Number(value); return value !== null && value !== '' && Number.isFinite(number) ? Math.min(.8, Math.max(.2, number)) : .5; };
  function storedSplitRatio() { try { return clampSplitRatio(localStorage.getItem(SPLIT_KEY)); } catch { return .5; } }
  const json = (path, options) => api.json ? api.json(path, options) : fetch(path, options).then(async r => { if (!r.ok) throw Error(await r.text()); return r.json(); });
  Object.assign(state, { diffIndex: 0, selectionBusy: false, generationKey: null });
  const text = id => ($(id) || {}).textContent || '';
  const fileName = file => String(file?.name || '').replace(/\\/g, '/').split('/').pop();
  const legacyDoc = file => /\.doc$/i.test(fileName(file));
  const legacyDocMessage = files => `检测到 Word 97-2003 格式（.doc）文件：${files.map(fileName).join('、')}。请用 Word/WPS 打开后“另存为” .docx，再重新选择。`;
  // FL-D856: every upload rejection code needs a readable cause and an honest
  // recovery path — a rejected slot cannot be replaced pre-seal (manifest binds
  // name+size), so the remedy is creating a fresh task.
  // 与服务端 FUNDLEX_MAX_UPLOAD_BYTES 默认值一致；超限仍以服务端校验为准（FL-D859）。
  const MAX_UPLOAD_BYTES = 25*1024*1024;
  const uploadErrorLabel = code => ({
    LEGACY_DOC_UNSUPPORTED:'请将 .doc 另存为 .docx 后重新选择',
    COMPARE_ENCRYPTED_DOCX:'文件有密码保护，请解除密码后新建对比任务上传',
    COMPARE_UNSUPPORTED_FORMAT:'仅支持 .docx 文件，请转换格式后新建对比任务上传',
    COMPARE_INVALID_DOCX:'文件不是可用的 .docx 文档，请检查后新建对比任务上传',
    COMPARE_UPLOAD_REJECTED:'文件未通过上传校验（可能超过大小限制），请处理后新建对比任务上传',
    MANIFEST_ENTRY_NOT_FOUND:'上传文件与任务清单不匹配，请新建对比任务上传',
    MANIFEST_FILE_MISMATCH:'替换文件与首次选择的文件名或大小不一致；如需更换文件，请新建对比任务上传',
    UPLOAD_IDENTITY_CONFLICT:'该文件位已有其他文件；如需更换，请新建对比任务上传',
  })[code] || code || '上传被拒';
  const relativePath = file => {
    const raw=String(file?.webkitRelativePath || '').replace(/\\/g, '/');
    if(raw) return raw.split('/').filter(Boolean).slice(1).join('/') || fileName(file);
    return fileName(file);
  };
  // FL-D980: parser coverage warnings 是机读 token（后端协议，测试锁定），
  // 用户必须看到可读的「哪部分内容未纳入比对」，不能直露 token。
  const COVERAGE_STORY_LABELS = {header:'页眉',footer:'页脚',footnote:'脚注',endnote:'尾注',comment:'批注'};
  const COVERAGE_MARKER_LABELS = {drawing:'图形/图片',pict:'图形',object:'嵌入对象',AlternateContent:'复合内容',txbxContent:'文本框',sym:'符号'};
  const coverageWarningLabel = w => {
    const m = /^UNSUPPORTED_VISIBLE_CONTENT:(.+)$/.exec(String(w||''));
    if(!m)return String(w||'');
    const parts=m[1].split(':');
    if(parts[0]==='table-wrapper')return `表格中的${COVERAGE_MARKER_LABELS[parts[1]]||parts[1]||'内容'}`;
    const story=COVERAGE_STORY_LABELS[parts[0]];
    if(story)return parts[1]?`${story}中的${COVERAGE_MARKER_LABELS[parts[1]]||'非文本内容'}`:`${story}内容`;
    return `正文中的${COVERAGE_MARKER_LABELS[parts[0]]||parts[0]}`;
  };
  function pairRow(pair = {}, index) {
    const selected = [pair.left?.name || fileName(pair._left), pair.right?.name || fileName(pair._right)].filter(Boolean).join(' / ');
    const sideCard=(side,title,badge)=>{
      const name=pair[side]?.name||fileName(pair[`_${side}`]);
      return `<div class="compare-file-card ${name?'has-file':''}" data-file-side="${side}"><div class="compare-file-card-title"><span class="compare-side-badge">${badge}</span><strong>${title}</strong></div><div class="compare-file-name" title="${esc(name)}">${esc(name||'尚未选择合同')}</div><div class="compare-file-card-action"><button type="button" class="btn btn-sm" data-compare-choose="${side}" aria-label="选择${title}">${name?'更换文件':'选择文件'}</button><span>仅支持 DOCX；.doc 请先另存为 .docx。带修订痕迹的文件可直接上传，按「接受全部修订」后的内容比对</span></div><input type="file" accept=".doc,.docx,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document" data-compare-${side}="${index}" aria-label="${title}" hidden></div>`;
    };
    return `<div class="compare-pair-input" data-pair-index="${index}"><div class="compare-pair-head"><strong>合同组 ${String(index+1).padStart(2,'0')}</strong><button type="button" class="btn-link" data-compare-remove="${index}" ${index?'':'disabled'}>移除本组</button></div><div class="compare-side-inputs">${sideCard('left','合同A','A')}${sideCard('right','合同B','B')}</div><p class="sr-only compare-file-label" data-compare-label="${index}">${esc(selected||'尚未选择文件')}</p></div>`;
  }
  function renderInputs() { const box=$('compare-pair-inputs'); if (box) box.innerHTML = (state.inputs || [{}]).map(pairRow).join(''); }
  function syncInputIndexes() { document.querySelectorAll('#compare-pair-inputs .compare-pair-input').forEach((row,i)=>{ row.dataset.pairIndex=String(i); row.querySelector('[data-compare-left]')?.setAttribute('data-compare-left',String(i)); row.querySelector('[data-compare-right]')?.setAttribute('data-compare-right',String(i)); row.querySelector('[data-compare-remove]')?.setAttribute('data-compare-remove',String(i)); }); }
  function selectedFiles() { return (state.inputs || []).map(x => ({ left: x._left || x.left, right: x._right || x.right })).filter(x => x.left || x.right); }
  function resetFolders() { state.folderLeft=[]; state.folderRight=[]; for(const id of ['compare-left-folder','compare-right-folder'])if($(id))$(id).value=''; }
  function showCreate(show=true) { $('compare-create').hidden = !show; if (show) { clearTimeout(state.poll); state.requestToken++; $('compare-detail').hidden=true; setViewerOpen(false); state.view=null; state.mergedMarks=state.leftMarks=state.rightMarks=null; state.uploadDraft=null; state.inputs=[{}]; resetFolders(); $('compare-upload-message').textContent=''; $('compare-retry').hidden=true; $('compare-lines')?.replaceChildren(); for(const pane of [$('compare-word-merged-pane'),$('compare-word-left-pane'),$('compare-word-right-pane'),$('compare-left-pane'),$('compare-right-pane')]){clearVirtual(pane);if(pane)pane.innerHTML='';} renderInputs(); } }
  function statusLabel(v) { return ({...(window.FUNDLEX_STATUS_LABELS||{}),pending:'待上传',succeeded:'已处理',incomplete:'覆盖不完整',failed:'失败',sealed:'已提交',completed:'已处理'}[v] || '—'); }
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
    const hasResult=state.pairs.some(p=>['succeeded','incomplete'].includes(p.status));
    const pendingNote=$('compare-pending-note'); if(pendingNote)pendingNote.hidden=hasResult;
  }
  function failureStageLabel(v) { return ({claim_setup:'开始处理',input_integrity:'文件检查',compare:'文本比对',heartbeat:'处理中',finish:'保存结果'} [v] || v || '未知阶段'); }
  function pairErrorLabel(p) {
    if (p.viewError) return p.viewError;
    if (!p.error_code) return '';
    // FL-D857: a sealed-incomplete pair carries no diagnostics; the truthful
    // cause lives in the per-file rejection codes the payload already delivers.
    if (p.error_code==='COMPARE_PAIR_INCOMPLETE') {
      const bad=['left','right'].map(side=>({side,file:p[side]})).filter(x=>!x.file||x.file.upload_status!=='accepted');
      if(!bad.length) return '该组文件不完整，请稍后重试';
      // FL-D983: 文件级原因自带的「新建对比任务上传」补救与尾句重复，
      // 尾句只补充「该组已判失败」的结论，不再重复补救路径。
      return bad.map(x=>{const tag=x.side==='left'?'合同A':'合同B';
        return x.file?.error_code?`${tag}：${uploadErrorLabel(x.file.error_code)}`:`${tag} 未成功上传`;
      }).join('；')+'。该组已判失败，须新建任务补救。';
    }
    const failure=p.diagnostics?.failure;
    if (!failure || failure.error_code!==p.error_code) return `处理失败，请稍后重试`;
    return `处理失败：${failureStageLabel(failure.stage)}环节出错${failure.retryable?'，可重试':'，请新建对比任务后重试；若仍失败请联系支持'}`;
  }
  function renderPairs() {
    $('compare-pair-list').innerHTML=`<div class="compare-pair-statuses">${state.pairs.map((p,i)=>`<button type="button" role="tab" aria-selected="${p.id===state.selectedPairId?'true':'false'}" class="compare-pair-status ${p.id===state.selectedPairId?'is-selected':''} ${['succeeded','incomplete'].includes(p.status)?'is-done':''} ${p.status==='incomplete'?'is-incomplete':''} ${p.status==='failed'||p.viewError?'is-failed':''}" data-compare-pair="${i}"><span class="compare-pair-number">${String(i+1).padStart(2,'0')}</span><span class="compare-pair-main"><strong>${esc(p.label||`第 ${i+1} 组`)}</strong><small>合同A：${esc(p.left?.name||'未命名')} / 合同B：${esc(p.right?.name||'未命名')}</small></span><span class="compare-pair-state">${esc(statusLabel(p.status))}${p.summary?` · ${p.summary.total} 处`:''}</span>${p.error_code||p.viewError?`<span class="compare-pair-error" role="status">${esc(pairErrorLabel(p))}</span>`:''}</button>`).join('')}</div>`;
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
        draft.acceptedRevisions=(draft.acceptedRevisions||0)+receipts.reduce((n,r)=>n+(r&&Number(r.revisions_accepted)>0?1:0),0);
        draft.next=i+1;
      }
      message.textContent='文件已上传，正在提交对比任务…'; await json(`/api/compare/tasks/${encodeURIComponent(draft.task.id)}/seal`,{method:'POST'}); if(identity!==state.identityToken)return;
      message.textContent='已提交，对比任务正在处理。'+(draft.acceptedRevisions>0?`其中 ${draft.acceptedRevisions} 份文件带修订痕迹，已按「接受全部修订」后的内容参与比对。`:''); state.uploadDraft=null; showCreate(false); await loadTasks(); await openTask(draft.task.id);
    } catch(e) { if(identity===state.identityToken){message.textContent=`上传中断：${e.message}。已完成的文件已保留，可点击“继续上传”。`; $('compare-retry').hidden=false;} }
    finally { if(identity===state.identityToken)$('compare-submit').disabled=false; }
  }
  async function createTask() {
    const files=selectedFiles(), message=$('compare-upload-message');
    const legacy=files.flatMap(x=>[x.left,x.right]).filter(f=>f&&legacyDoc(f));
    if(legacy.length){message.textContent=legacyDocMessage(legacy);return;}
    // FL-D859: 超大文件在客户端先拦截——服务端拒绝后同清单不可替换，只能新建任务。
    const oversize=files.flatMap(x=>[x.left,x.right]).filter(f=>f&&f.size>MAX_UPLOAD_BYTES);
    if(oversize.length){message.textContent=`单个文件最大 25MB，超出：${oversize.map(fileName).join('、')}。请压缩或拆分后重新选择。`;return;}
    if (!files.length || files.some(x=>!x.left||!x.right)) { message.textContent='每组都需要同时选择合同A和合同B的 DOCX 文件。'; return; }
    const identity=state.identityToken; const name=($('compare-name').value||'').trim()||`合同比对 ${new Date().toLocaleString('zh-CN',{hour12:false})}`; const pairs=files.map((x,i)=>{const leftId=`L${i}-${crypto.randomUUID()}`,rightId=`R${i}-${crypto.randomUUID()}`;return {client_pair_id:`P${i+1}`,label:`合同 ${i+1}`,left:{client_id:leftId,name:fileName(x.left),size:x.left.size},right:{client_id:rightId,name:fileName(x.right),size:x.right.size}};});
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
    const scheduleAlign = () => {
      clearTimeout(state.splitAlignTimer);
      state.splitAlignTimer = setTimeout(alignPanels, 120);
    };
    const finish = apply => {
      if (!dragging) return;
      dragging = false; state.splitDragging = false;
      gutter.classList.remove('is-dragging');
      if (preview) { preview.style.left = ''; preview.style.opacity = ''; }
      window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', onUp); window.removeEventListener('pointercancel', onCancel);
      applySplitRatio(apply ? state.pendingSplitRatio : state.splitRatio, true); refreshVirtualLayouts(); drawLines();
      // The re-wrap above invalidates every pane's own anchor; re-align the
      // panes through the block-index model so the correspondence survives
      // the width change (FL-D841).
      if (apply) scheduleAlign();
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
    gutter.addEventListener('dblclick', () => { applySplitRatio(.5); refreshVirtualLayouts(); drawLines(); scheduleAlign(); });
    gutter.addEventListener('keydown', event => {
      const step = event.shiftKey ? .05 : .02; let next = state.splitRatio;
      if (event.key === 'ArrowLeft') next -= step;
      else if (event.key === 'ArrowRight') next += step;
      else if (event.key === 'Home') next = .2;
      else if (event.key === 'End') next = .8;
      else if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); applySplitRatio(.5); refreshVirtualLayouts(); drawLines(); scheduleAlign(); return; }
      else return;
      event.preventDefault(); applySplitRatio(next);
      // Keyboard nudges reflow too, but each keystroke must not pay for a
      // full re-measure; debounce the heavy pass (FL-D840/FL-D841).
      clearTimeout(state.splitRefreshTimer);
      state.splitRefreshTimer = setTimeout(() => { refreshVirtualLayouts(); drawLines(); alignPanels(); }, 200);
    });
    applySplitRatio(storedSplitRatio(), false);
  }
  function bindPanelSplitters() {
    if (!window.FundLexColumnSplitter) return;
    let frame = null, alignTimer = null;
    const dragging = () => [$('compare-rail-splitter'), $('compare-word-splitter')].some(h => h?.classList.contains('is-dragging'));
    const refresh = (final = false) => {
      state.diffPositions = null;
      if (!final && dragging()) {
        // Width changes continuously while dragging; the browser reflows the
        // text on its own. Re-measuring every pane per frame here is what
        // made the splitter drag stutter (FL-D840), so only the fallback
        // line redraw stays live and the heavy pass runs once on pointerup.
        setLinesScrolling(true);
        drawLines();
        return;
      }
      setLinesScrolling(false);
      if (!frame) frame = requestAnimationFrame(() => {
        frame = null;
        refreshVirtualLayouts();
        drawLines();
      });
      clearTimeout(alignTimer);
      alignTimer = setTimeout(alignPanels, 120);
    };
    window.FundLexColumnSplitter($('compare-rail-splitter'), $('compare-view-body'), document.querySelector('.compare-word-revisions'), {
      key: 'fundlex-compare-revisions-width',
      variable: '--compare-revisions-width',
      min: 220, max: 660, minOther: 480, fallback: 300,
      side: () => state.viewMode === 'classic' ? 'right' : 'left',
      disabled: () => matchMedia('(max-width: 760px)').matches,
      onChange: () => refresh(false),
      onEnd: () => refresh(true),
    });
    window.FundLexColumnSplitter($('compare-word-splitter'), $('compare-word-layout'), $('compare-word-sources'), {
      key: 'fundlex-compare-sources-width',
      variable: '--compare-sources-width',
      min: 240, max: 720, minOther: 480, fallback: 360,
      side: 'right',
      disabled: () => matchMedia('(max-width: 760px)').matches,
      onChange: () => refresh(false),
      onEnd: () => refresh(true),
    });
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
      const leftMarks=left._virtualDoc?.marks,rightMarks=right._virtualDoc?.marks;
      if(!leftMarks||!rightMarks)return;
      const active=visibleDiffs()[state.diffIndex]?.id;
      const leftTop=left.scrollTop,leftBottom=leftTop+left.clientHeight,rightTop=right.scrollTop,rightBottom=rightTop+right.clientHeight;
      const fragment=document.createDocumentFragment(); let count=0;
      for(const d of state.view.diffs||[]){
        const lm=leftMarks.get(d.id),rm=rightMarks.get(d.id);
        if(!lm||!rm)continue;
        if(d.id!==active){
          const above=lm.top+lm.height<leftTop-80&&rm.top+rm.height<rightTop-80;
          const below=lm.top>leftBottom+80&&rm.top>rightBottom+80;
          if(above||below)continue;
        }
        const x1=lr.left-cr.left+lm.rightX,y1=lr.top-cr.top+(lm.top-leftTop)+lm.height/2;
        const x2=rr.left-cr.left+rm.leftX,y2=rr.top-cr.top+(rm.top-rightTop)+rm.height/2;
        if(d.id!==active&&((y1<-40&&y2<-40)||(y1>cr.height+40&&y2>cr.height+40)))continue;
        const path=document.createElementNS('http://www.w3.org/2000/svg','path');
        path.setAttribute('d',`M ${x1} ${y1} C ${(x1+x2)/2} ${y1}, ${(x1+x2)/2} ${y2}, ${x2} ${y2}`);
        path.dataset.diffId=d.id;path.classList.toggle('active',d.id===active);fragment.append(path);
        if(++count>=240)break;
      }
      svg.setAttribute('viewBox',`0 0 ${cr.width} ${cr.height}`);
      svg.replaceChildren(fragment);
    });
  }
  function setLinesScrolling(on) {
    // Fade the connector lines while a scroll gesture is in flight; they are
    // recomputed once scrolling settles instead of being rebuilt every frame
    // (FL-D840). The class is only meaningful in the classic view.
    if (state.linesScrolling === on) return;
    state.linesScrolling = on;
    $('compare-viewer')?.classList.toggle('is-sync-scrolling', on);
  }
  function drawLinesDeferred() {
    if ($('compare-classic-view')?.hidden || $('compare-viewer')?.hidden) return;
    setLinesScrolling(true);
    clearTimeout(state.lineSettle);
    state.lineSettle = setTimeout(() => { setLinesScrolling(false); drawLines(); }, 90);
  }
  function visiblePanels() {
    return allPanels().filter(pane => pane.offsetParent !== null && pane.clientHeight > 0);
  }
  function buildAlignmentModel() {
    const left = state.docs?.left, right = state.docs?.right, merged = state.docs?.merged;
    if (!left || !right) return null;
    const lookup = doc => {
      if (doc.blockIndex) return doc.blockIndex;
      const index = new Map();
      doc.blocks.forEach((block, position) => {
        [block.blockId, ...(block.blockIds || []), ...(block.diffIds || [])].filter(Boolean)
          .forEach(id => index.set(id, position));
      });
      return index;
    };
    const leftLookup = lookup(left), rightLookup = lookup(right);
    const anchors = [{left: 0, right: 0}];
    const groups=state.view?.alignment||[];
    for(const group of groups){
      const ls=(group.left||[]).map(id=>leftLookup.get(id)).filter(Number.isInteger);
      const rs=(group.right||[]).map(id=>rightLookup.get(id)).filter(Number.isInteger);
      if(!ls.length||!rs.length)continue;
      const count=Math.max(ls.length,rs.length);
      for(let i=0;i<count;i++)anchors.push({left:ls[Math.min(ls.length-1,Math.floor(i*ls.length/count))],right:rs[Math.min(rs.length-1,Math.floor(i*rs.length/count))]});
    }
    for (const diff of groups.length?[]:state.view?.diffs || []) {
      const leftBlock = diff.left?.block_id || diff.left_anchor?.block_id || diff.left_spans?.[0]?.block_id;
      const rightBlock = diff.right?.block_id || diff.right_anchor?.block_id || diff.right_spans?.[0]?.block_id;
      const leftIndex = leftLookup.get(leftBlock);
      const rightIndex = rightLookup.get(rightBlock);
      if (Number.isInteger(leftIndex) && Number.isInteger(rightIndex)) {
        anchors.push({left: leftIndex, right: rightIndex});
      }
    }
    anchors.push({left: left.blocks.length - 1, right: right.blocks.length - 1});
    anchors.sort((a, b) => a.left - b.left || a.right - b.right);
    const clean = [];
    let lastRight = -1;
    for (const anchor of anchors) {
      if (anchor.left < 0 || anchor.right < 0) continue;
      if (anchor.right <= lastRight && anchor.right !== clean[clean.length - 1]?.right) continue;
      clean.push(anchor);
      lastRight = Math.max(lastRight, anchor.right);
    }
    if (!clean.length || clean[0].left !== 0 || clean[0].right !== 0) clean.unshift({left: 0, right: 0});
    const end = {left: left.blocks.length - 1, right: right.blocks.length - 1};
    if (clean[clean.length - 1].left !== end.left || clean[clean.length - 1].right !== end.right) clean.push(end);

    const rightToMerged = new Array(right.blocks.length).fill(-1);
    const mergedToRight = new Array(merged?.blocks.length || 0).fill(-1);
    if (merged) {
      const mergedRightIndex = lookup(merged);
      right.blocks.forEach((block, index) => {
        const value = mergedRightIndex.get(block.blockId);
        if (Number.isInteger(value)) rightToMerged[index] = value;
      });
      let previous = 0;
      for (let i = 0; i < rightToMerged.length; i++) {
        if (rightToMerged[i] < 0) rightToMerged[i] = previous;
        else previous = rightToMerged[i];
      }
      const rightIndexByBlock = rightLookup;
      let nearest = 0;
      for (let i = 0; i < mergedToRight.length; i++) {
        const value = rightIndexByBlock.get(merged.blocks[i].blockId);
        if (Number.isInteger(value)) { mergedToRight[i] = value; nearest = value; }
        else mergedToRight[i] = nearest;
      }
      for (let i = 1; i < rightToMerged.length; i++) rightToMerged[i] = Math.max(rightToMerged[i], rightToMerged[i - 1]);
      for (let i = 1; i < mergedToRight.length; i++) mergedToRight[i] = Math.max(mergedToRight[i], mergedToRight[i - 1]);
    }
    const model={anchors: clean, rightToMerged, mergedToRight};
    const mergedLookup=merged?lookup(merged):new Map();
    model.leftToMerged=left.blocks.map((block,i)=>mergedLookup.get(block.blockId)??rightToMerged[mapAnchorIndex(i,'left','right',model)]);
    model.mergedToLeft=(merged?.blocks||[]).map((block,i)=>leftLookup.get(block.blockId)??mapAnchorIndex(mergedToRight[i],'right','left',model));
    return model;
  }
  function alignmentModel() {
    if (state.alignment === null) state.alignment = buildAlignmentModel();
    return state.alignment;
  }
  function mapAnchorIndex(index, from, to, model) {
    const anchors = model.anchors;
    if (!anchors.length) return index;
    if (index <= anchors[0][from]) return anchors[0][to];
    for (let i = 1; i < anchors.length; i++) {
      const a = anchors[i - 1], b = anchors[i];
      if (index <= b[from]) {
        if (b[from] === a[from]) return b[to];
        const ratio = (index - a[from]) / (b[from] - a[from]);
        return Math.round(a[to] + ratio * (b[to] - a[to]));
      }
    }
    return anchors[anchors.length - 1][to];
  }
  function syncPaneScroll(source) {
    if(state.focusScrolling){drawLines();return;}
    if (window.matchMedia('(max-width: 760px)').matches) { drawLines(); return; }
    if (state.syncTargets.has(source)) { drawLinesDeferred(); return; }
    if (state.scrollFrame !== null) { drawLinesDeferred(); return; }
    const targets = visiblePanels().filter(p => p !== source);
    if (!targets.length) return;
    state.scrollSource = source;
    state.scrollFrame = requestAnimationFrame(() => {
      state.scrollFrame = null;
      targets.forEach(target => state.syncTargets.add(target));
      const sourceDoc = source._virtualDoc;
      const view=state.view;
      sourceDoc?.refresh(false);
      const anchor = sourceDoc?.visibleBlock?.();
      const model = alignmentModel();
      if (anchor && model) {
        // Align by paragraph position, not by scrollbar ratio. Diff anchors
        // give the correspondence between the two source documents; merged
        // blocks then map through the right-side block id.
        let leftIndex = anchor.index, rightIndex = anchor.index;
        if (source.id === 'compare-word-merged-pane') {
          rightIndex = model.mergedToRight[anchor.index] ?? anchor.index;
          leftIndex = model.mergedToLeft[anchor.index];
        } else if (source.id === 'compare-word-left-pane' || source.id === 'compare-left-pane') {
          rightIndex = mapAnchorIndex(leftIndex, 'left', 'right', model);
        } else {
          leftIndex = mapAnchorIndex(rightIndex, 'right', 'left', model);
        }
        const targetIndex = target => {
          if (target.id === 'compare-word-merged-pane') return source.id.includes('left')?model.leftToMerged[leftIndex]:model.rightToMerged[rightIndex] ?? rightIndex;
          if (target.id === 'compare-word-left-pane' || target.id === 'compare-left-pane') return leftIndex;
          return rightIndex;
        };
        targets.forEach(target => {
          const doc = target._virtualDoc;
          if (!doc) return;
          if (doc.scrollToBlockIndexEstimate) doc.scrollToBlockIndexEstimate(targetIndex(target), anchor.fraction);
          else if (doc.scrollToBlockIndex) doc.scrollToBlockIndex(targetIndex(target), anchor.fraction, false);
        });
        clearTimeout(state.syncSettle);
        state.syncSettle = setTimeout(() => {
          if(state.view!==view||source._virtualDoc!==sourceDoc||!source.clientHeight)return;
          const latest = sourceDoc?.visibleBlock?.();
          const currentModel = alignmentModel();
          if (!latest || !currentModel) return;
          let latestLeft = latest.index, latestRight = latest.index;
          if (source.id === 'compare-word-merged-pane') {
            latestRight = currentModel.mergedToRight[latest.index] ?? latest.index;
            latestLeft = currentModel.mergedToLeft[latest.index];
          } else if (source.id === 'compare-word-left-pane' || source.id === 'compare-left-pane') {
            latestRight = mapAnchorIndex(latestLeft, 'left', 'right', currentModel);
          } else {
            latestLeft = mapAnchorIndex(latestRight, 'right', 'left', currentModel);
          }
          targets.forEach(target => {
            const doc = target._virtualDoc;
            if (!doc?.scrollToBlockIndex) return;
            const index = target.id === 'compare-word-merged-pane'
              ? (source.id.includes('left')?currentModel.leftToMerged[latestLeft]:currentModel.rightToMerged[latestRight] ?? latestRight)
              : target.id === 'compare-word-left-pane' || target.id === 'compare-left-pane'
                ? latestLeft : latestRight;
            // Verify before forcing: while the gesture is still running this
            // settle fires every 150 ms; panes already on the target block
            // must not pay for scrollToBlockIndex's force refreshes (FL-D840).
            const current = doc.visibleBlock?.();
            if (current && current.index === index && Math.abs(current.fraction - latest.fraction) < .25) return;
            doc.scrollToBlockIndex(index, latest.fraction, false);
          });
        }, 150);
      } else if (anchor) {
        const sourceLast = Math.max(1, sourceDoc.blocks.length - 1);
        const ratio = anchor.index / sourceLast;
        targets.forEach(target => {
          const doc = target._virtualDoc;
          if (!doc?.scrollToBlockIndex) return;
          const targetLast = Math.max(1, doc.blocks.length - 1);
          doc.scrollToBlockIndex(Math.round(ratio * targetLast), anchor.fraction, false);
        });
      } else {
        const sourceMax = Math.max(0, source.scrollHeight - source.clientHeight);
        const ratio = sourceMax ? source.scrollTop / sourceMax : 0;
        targets.forEach(target => {
          const targetMax = Math.max(0, target.scrollHeight - target.clientHeight);
          target.scrollTop = ratio * targetMax;
        });
      }
      drawLinesDeferred();
      clearTimeout(state.syncRelease);
      state.syncRelease=setTimeout(() => {
        state.syncTargets.clear();
        state.scrollSource = null;
        setLinesScrolling(false);
        drawLines();
      }, 220);
    });
  }
  function alignPanels() {
    if (!state.view || $('compare-viewer').hidden) return;
    const source = state.viewMode === 'classic' ? $('compare-left-pane') : $('compare-word-merged-pane');
    if (source) syncPaneScroll(source);
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
    state.selectionDirty=false;state.selectionSaving=false;state.selectionBusy=false;state.selectionSaved=false;state.generationKey=null;
    selectionStatus('');$('compare-selection-downloads')?.replaceChildren();renderSelection();syncSelectionControls();
  }
  function renderSelectionDownloads() {
    const box=$('compare-selection-downloads'); if(!box)return;
    const artifacts=state.selectionDirty?[]:(state.selection?.artifacts||[]);
    if(!artifacts.length){box.replaceChildren();return;}
    // FL-D984: 后端产物 kind 恒为 final/redline（store.SELECTION_KINDS），
    // 旧标签表的 selected_* 键名从不命中，下载按钮直露裸 kind。
    const labels={final:'下载选择结果 DOCX',redline:'下载选择结果（带修订痕迹）DOCX',selected_final:'下载选择结果 DOCX',selected_redline:'下载选择结果（带修订痕迹）DOCX',selection_report_markdown:'下载选择报告（Markdown）',selection_report_json:'下载选择报告（JSON）'};
    box.innerHTML=artifacts.map(item=>{const isDocx=item.kind.endsWith('docx')||['final','redline'].includes(item.kind);return `<div class="compare-artifact"><button class="btn btn-sm" type="button" data-selection-download="${esc(item.download_url)}" data-selection-filename="${esc(`compare-v${item.version}-${item.kind}${isDocx?'.docx':''}`)}" ${item.status==='stale'?'title="该版本已过期，仅作追溯"':''}>${esc(labels[item.kind]||item.kind)} · v${item.version}${item.status==='stale'?' · 已过期':''}</button></div>`;}).join('');
  }
  function renderSelection() {
    const s=state.selection, node=$('compare-selection-progress'), buttons=document.querySelectorAll('#compare-selection-left-all,#compare-selection-right-all,#compare-selection-generate,#compare-selection-save,#compare-selection-pending');
    if(!s){if(node)node.textContent='正在读取选择状态…';buttons.forEach(x=>{x.disabled=true;});return;}
    const {counts,total,pending}=selectionCounts();
    if(node)node.textContent=`已选择 ${total-pending} / ${total} 处 · 待选择 ${pending}`;
    const ready=selectionCanGenerate();
    const blocked=selectionIssues().some(x=>x.blocking), busy=state.selectionSaving||state.selectionBusy;
    $('compare-selection-issues').textContent=selectionIssues().filter(x=>x.blocking).map(x=>x.detail||x.code).join(' ');
    const generate=$('compare-selection-generate');
    if(generate){generate.disabled=!ready;generate.title=pending?'所有差异都需要明确选择合同A或合同B':blocked?'当前结果包含暂不支持的结构':'生成选择结果';}
    buttons.forEach(x=>{if(x!==generate)x.disabled=busy;});
    $('compare-selection-save').disabled=busy||!state.selectionDirty;
    $('compare-selection-pending').disabled=busy||!pending;
    for(const side of ['left','right'])$(`compare-selection-${side}-all`).textContent=`全部采用 ${side==='left'?'A':'B'}`;
    renderSelectionDownloads();
  }
  async function loadSelection(pairId) {
    resetSelection();const token=state.selectionToken;
    try { const payload=await json(`/api/compare/pairs/${encodeURIComponent(pairId)}/selection`); if(token!==state.selectionToken||pairId!==state.selectedPairId)return; state.selection=normalizeSelection(payload);state.selectionDraft={...(state.selection?.decisions||{})};state.selectionSaved=(state.selection?.selection_epoch??0)>=1;renderSelection();syncSelectionControls(); }
    catch(e){if(token===state.selectionToken){selectionStatus(`读取选择状态失败：${e.message}`,true);renderSelection();}}
  }
  async function saveSelectionDraft(updateIds) {
    const ids=Array.isArray(updateIds)?updateIds:null;
    const binding=selectionBinding(); if(!binding||!state.selectionDraft)return;
    if(state.selectionSaving||state.selectionBusy)return;
    const context=selectionContext(), token=++state.selectionSaveToken, decisions={...state.selectionDraft};
    state.selectionSaving=true;state.selectionDirty=true;
    try {
      selectionStatus('正在保存选择…');renderSelection();if(ids)ids.forEach(updateSelectionItem);else syncSelectionControls();
      const payload=await json(`/api/compare/pairs/${encodeURIComponent(context.pairId)}/selection`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({...binding,decisions})});
      if(!selectionCurrent(context)||token!==state.selectionSaveToken)return;
      state.selection=normalizeSelection(payload);state.selectionDraft={...(state.selection?.decisions||{})};state.selectionDirty=false;state.selectionSaved=true;state.generationKey=null;selectionStatus('已保存');
    } catch(e) {
      if(!selectionCurrent(context)||token!==state.selectionSaveToken)return;
      if(e.raw==='SELECTION_EPOCH_CONFLICT') {
        try {
          const latest=await json(`/api/compare/pairs/${encodeURIComponent(context.pairId)}/selection`);
          if(!selectionCurrent(context)||token!==state.selectionSaveToken)return;
          if(['result_sha256','left_source_sha256','right_source_sha256'].every(k=>latest[k]===state.selection[k])){state.selection=normalizeSelection(latest);state.selectionSaved=(state.selection?.selection_epoch??0)>=1;}
        } catch { /* Keep the local map; a failed reload must not discard it. */ }
      }
      if(selectionCurrent(context)){state.selectionDirty=true;selectionStatus('保存未完成，本地选择已保留。请核对后点击“保存当前选择”重试。',true);}
    } finally {if(selectionCurrent(context)&&token===state.selectionSaveToken){state.selectionSaving=false;renderSelection();if(ids)ids.forEach(updateSelectionItem);else syncSelectionControls();}}
  }
  function chooseSelection(id, choice) { if(!state.selection||state.selectionSaving||state.selectionBusy)return; state.selectionDraft={...(state.selectionDraft||{}),[id]:choice};state.selectionDirty=true;updateSelectionItem(id);saveSelectionDraft([id]); }
  function setAllSelections(choice) { if(!state.selection||state.selectionSaving||state.selectionBusy)return; const next={};(state.view?.diffs||[]).forEach(item=>{next[item.id]=choice;});state.selectionDraft=next;state.selectionDirty=true;syncSelectionControls();saveSelectionDraft(); }
  async function selectionAction(kind) {
    const binding=selectionBinding();if(!binding||state.selectionSaving||state.selectionBusy||state.selectionDirty||(kind==='generate'&&!selectionCanGenerate()))return;
    if(kind==='generate'&&binding.expected_epoch<1&&!state.selectionSaved){selectionStatus('请先保存当前选择，再生成选择结果。',true);return;}
    const context=selectionContext();state.selectionBusy=true;
    selectionStatus('正在生成选择结果 DOCX，请稍候…');renderSelection();syncSelectionControls();
    const headers={'Content-Type':'application/json'};
    if(kind==='generate'){state.generationKey ||= `compare-${crypto.randomUUID()}`;headers['Idempotency-Key']=state.generationKey;}
    try {
      // 预览可生成性按钮已随 FL-D844 删除：点「生成选择结果」即由服务端校验，
      // 阻塞原因经 selection-issues / selection-status 内联展示。
      const body={expected_epoch:binding.expected_epoch,decision_hash:state.selection?.draft?.decision_hash||state.selection?.decision_hash||'',result_sha256:binding.result_sha256};
      const result=await json(`/api/compare/pairs/${encodeURIComponent(context.pairId)}/selection/${kind}`,{method:'POST',headers,body:JSON.stringify(body)});
      if(!selectionCurrent(context))return;
      if(kind==='generate'){
        const latest=normalizeSelection(await json(`/api/compare/pairs/${encodeURIComponent(context.pairId)}/selection`));
        if(!selectionCurrent(context))return;
        state.selection=latest;state.selectionDraft={...(latest?.decisions||{})};state.selectionDirty=false;state.generationKey=null;
        selectionStatus(`已生成版本 ${result.version}，可下载选择结果、带修订痕迹的选择结果和报告。`);
      }
    } catch(e){if(selectionCurrent(context))selectionStatus(e.raw||e.message,true);}
    finally {if(selectionCurrent(context)){state.selectionBusy=false;renderSelection();syncSelectionControls();}}
  }
  const generateSelection=()=>selectionAction('generate');
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
    if (next === 'word' && state.view && !state.wordSourcesRendered && !$('compare-word-layout')?.classList.contains('is-sources-hidden')) renderWordSources();
    if (next === 'classic') applySplitRatio(state.splitRatio, false);
    requestAnimationFrame(() => { refreshVirtualLayouts(); drawLines(); if (state.view) focusDiff(state.diffIndex); });
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
    cancelAnimationFrame(state.scrollFrame);state.scrollFrame=null;
    clearTimeout(state.syncSettle);state.syncTargets.clear();state.focusScrolling=true;
    const ds=visibleDiffs();
    document.querySelectorAll('.compare-diff.is-active,.compare-diff-item.is-active,.compare-ins.is-active,.compare-del.is-active').forEach(n=>n.classList.remove('is-active'));
    if(!ds.length){$('compare-diff-counter').textContent='0 / 0';state.focusScrolling=false;return;}
    state.diffIndex=(index+ds.length)%ds.length;const id=ds[state.diffIndex].id,diff=ds[state.diffIndex];
    const selector=`[data-diff-id="${CSS.escape(id)}"]`;
    const paneIds=[...WORD_PANES,...CLASSIC_PANES];
    const blockFor=side=>{
      const span=side==='left'?diff.left:diff.right;
      const anchor=side==='left'?diff.left_anchor:diff.right_anchor;
      const spans=side==='left'?diff.left_spans:diff.right_spans;
      return span?.block_id||anchor?.block_id||spans?.[0]?.block_id||'';
    };
    const scrolled=new Set();
    const findBlock=(paneId,side)=>{
      const pane=$(paneId);if(!pane||!pane._virtualDoc||!pane.clientHeight)return;
      const blockId=blockFor(side)||blockFor(side==='left'?'right':'left');
      if(blockId&&pane._virtualDoc.scrollToBlock(blockId)){scrolled.add(paneId);return;}
      if(pane._virtualDoc.scrollToBlock(id))scrolled.add(paneId);
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
    for(const paneId of paneIds){
      if(scrolled.has(paneId))continue;
      const pane=$(paneId),target=pane?.querySelector(selector);
      if(!pane||!target||!pane.clientHeight)continue;
      const pr=pane.getBoundingClientRect(),tr=target.getBoundingClientRect();
      if(tr.top<pr.top+8||tr.bottom>pr.bottom-8)pane.scrollTop+=tr.top+tr.height/2-pr.top-pr.height/2;
    }
    requestAnimationFrame(()=>requestAnimationFrame(()=>{state.focusScrolling=false;}));
    requestAnimationFrame(drawLines);
  }
  const DIFF_ITEM_HEIGHT=44, DIFF_RENDER_COUNT=24;
  function diffItemHtml(x,index,choice,disabled){
    const kind=x.type==='modify'?'修改':x.type==='insert'?'插入':'删除';
    return `<div class="compare-diff-item ${choice!=='pending'?'is-selected-choice':''}" data-compare-diff="${esc(x.id)}"><button type="button" class="compare-diff-jump" data-compare-diff="${esc(x.id)}"><span class="compare-diff-index">${index+1}</span><span class="compare-diff-kind is-${esc(x.type)}">${esc(kind)}</span><span class="compare-diff-preview"><span>${esc(x.section||'正文')} · ${esc(x.left?.text||'')} ${x.right?.text?'→ '+esc(x.right.text):''}</span></span></button><div class="compare-choice" role="group" aria-label="${esc(x.id)} 采用 A 或 B"><label class="${choice==='left'?'is-checked':''}"><input type="radio" name="choice-${esc(x.id)}" value="left" data-selection-choice="left" data-diff-id="${esc(x.id)}" ${choice==='left'?'checked':''} ${disabled?'disabled':''} title="采用合同A此版本">A</label><label class="${choice==='right'?'is-checked':''}"><input type="radio" name="choice-${esc(x.id)}" value="right" data-selection-choice="right" data-diff-id="${esc(x.id)}" ${choice==='right'?'checked':''} ${disabled?'disabled':''} title="采用合同B此版本">B</label></div></div>`;
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
      const ids=[...element.querySelectorAll('[data-block-id],[data-diff-id]')];
      const blockIds=ids.map(node=>node.getAttribute('data-block-id')||'').filter(Boolean);
      const diffIds=ids.map(node=>node.getAttribute('data-diff-id')||'').filter(Boolean);
      const blockId=element.getAttribute('data-block-id')||blockIds[0]||'';
      return {html:element.outerHTML,blockId,blockIds,diffIds,textLength:text.length,kind:tag==='table'?'table':heading?'heading':'paragraph'};
    });
    return {style:wrapper.getAttribute('style')||'',blocks};
  }
  class VirtualDocument {
    constructor(container,document,options={}) {
      this.container=container; this.blocks=document.blocks||[]; this.style=document.style||'';
      this.chunkSize=options.chunkSize||20; this.overscan=options.overscan||2;
      this.charsPerLine=options.charsPerLine||46; this.merged=Boolean(options.merged);
      this.collectMarks=Boolean(options.collectMarks); this.marks=new Map();
      this.onChange=options.onChange||null; this.chunks=[]; this.first=0; this.last=0; this.frame=null; this.anchorLockUntil=0;
      this.blockIndex=new Map(); this.blocks.forEach((block,index)=>[block.blockId,...(block.blockIds||[]),...(block.diffIds||[])].filter(Boolean).forEach(id=>this.blockIndex.set(id,index)));
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
      this.scale=Number.parseFloat(getComputedStyle(wrapper).zoom)||1;
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
    refresh(force,forcedRange){
      if(!this.chunks.length)return;
      const [first,last]=forcedRange||this.currentRange(this.container.scrollTop,this.container.clientHeight||600);
      if(!force&&first===this.first&&last===this.last)return;
      // Fast path: a forced refresh that would not mount, unmount or
      // re-measure anything is a no-op. scrollToBlockIndex settles and the
      // scroll-sync settle pass hit this constantly during linked scrolling
      // (FL-D840); without it every call pays for two full layout passes.
      if(first===this.first&&last===this.last){
        let dirty=false;
        for(let i=first;i<last;i++){const chunk=this.chunks[i];if(!chunk.el||!chunk.measured){dirty=true;break;}}
        if(!dirty)return;
      }
      const anchor=this.anchor(),anchorTop=this.totalBefore(anchor.index);
      const visible=!forcedRange?this.visibleBlock():null;
      const visibleNode=visible?this.chunks.find(chunk=>visible.index>=chunk.start&&visible.index<chunk.end)?.el?.children[visible.index%this.chunkSize]:null;
      const visibleY=visibleNode?.getBoundingClientRect().top;
      const previousScroll=this.container.scrollTop;
      // Keep the scroll range alive while replacing mounted chunks. Otherwise
      // the browser clamps scrollTop before the new spacers are installed.
      this.wrapper.style.minHeight=`${this.container.scrollHeight/this.scale}px`;
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
      if(this.collectMarks){
        // Collect diff-anchor geometry in the same layout pass as chunk
        // measurement. drawLines reads this map instead of forcing its own
        // 240-rect recache after every invalidation (FL-D840 classic view).
        const paneRect=this.container.getBoundingClientRect(),scrollTop=this.container.scrollTop;
        const marks=new Map();
        for(const node of this.windowEl.querySelectorAll('[data-diff-id]')){
          const r=node.getBoundingClientRect();
          marks.set(node.dataset.diffId,{top:r.top-paneRect.top+scrollTop,height:r.height,leftX:r.left-paneRect.left,rightX:r.right-paneRect.left});
        }
        this.marks=marks;
      }
      this.top.style.height=`${this.totalBefore(first)/this.scale}px`;
      this.bottom.style.height=`${this.totalAfter(last)/this.scale}px`;
      this.wrapper.style.minHeight='';
      this.container.scrollTop=previousScroll;
      const retained=visible?this.chunks.find(chunk=>visible.index>=chunk.start&&visible.index<chunk.end)?.el?.children[visible.index%this.chunkSize]:null;
      if(retained&&visibleY!==undefined){
        this.container.scrollTop+=retained.getBoundingClientRect().top-visibleY;
      }else if(anchor.index>=first&&anchor.index<last&&performance.now()>=this.anchorLockUntil){
        const nextTop=this.totalBefore(anchor.index);
        if(Math.abs(nextTop-anchorTop)>.5)this.container.scrollTop=nextTop+anchor.offset;
      }
      if(this.onChange)this.onChange();
    }
    resetMeasurements(){
      for(const chunk of this.chunks){chunk.measured=false;}
    }
    visibleBlock(){
      const top=this.container.scrollTop, paneRect=this.container.getBoundingClientRect();
      for(let ci=this.first;ci<this.last;ci++){
        const chunk=this.chunks[ci], host=chunk?.el;
        if(!host)continue;
        for(let offset=0;offset<host.children.length;offset++){
          const node=host.children[offset], rect=node.getBoundingClientRect();
          const nodeTop=rect.top-paneRect.top+top;
          if(nodeTop+rect.height>top+1){
            const index=Math.min(this.blocks.length-1,chunk.start+offset);
            return {index,fraction:Math.max(0,Math.min(1,(top-nodeTop)/Math.max(1,rect.height)))};
          }
        }
      }
      return null;
    }
    scrollToBlockIndexEstimate(index,fraction=0){
      if(!this.blocks.length)return;
      const targetIndex=Math.max(0,Math.min(this.blocks.length-1,Math.round(index)));
      let chunkIndex=0;
      for(let i=0;i<this.chunks.length;i++){if(targetIndex<this.chunks[i].end){chunkIndex=i;break;}}
      const chunk=this.chunks[chunkIndex];
      let top=this.totalBefore(chunkIndex);
      for(let i=chunk.start;i<targetIndex;i++)top+=this.estimate(this.blocks[i]);
      const height=this.estimate(this.blocks[targetIndex]);
      this.anchorLockUntil=performance.now()+220;
      this.container.scrollTop=Math.max(0,top+Math.max(0,Math.min(1,fraction))*height);
    }
    scrollToBlockIndex(index,fraction=0,settle=true){
      if(!this.blocks.length)return false;
      this.anchorLockUntil=performance.now()+220;
      const targetIndex=Math.max(0,Math.min(this.blocks.length-1,Math.round(index)));
      let chunkIndex=0;
      for(let i=0;i<this.chunks.length;i++){if(targetIndex<this.chunks[i].end){chunkIndex=i;break;}}
      const chunk=this.chunks[chunkIndex];
      const range=[Math.max(0,chunkIndex-1),Math.min(this.chunks.length,chunkIndex+2)];
      const place=()=>{
        const target=chunk?.el?.children[targetIndex-chunk.start];
        if(!target)return false;
        const paneRect=this.container.getBoundingClientRect(),targetRect=target.getBoundingClientRect();
        const targetTop=targetRect.top-paneRect.top+this.container.scrollTop;
        this.container.scrollTop=Math.max(0,targetTop+Math.max(0,Math.min(1,fraction))*targetRect.height);
        return true;
      };
      this.refresh(true,range);
      const found=place();
      this.refresh(true);place();
      if(settle)requestAnimationFrame(()=>{this.refresh(true);place();});
      return found;
    }
    scrollToBlock(blockId){
      const index=this.blockIndex.get(blockId);if(index===undefined)return false;
      let chunkIndex=0;for(let i=0;i<this.chunks.length;i++){if(index<this.chunks[i].end){chunkIndex=i;break;}}
      const range=[Math.max(0,chunkIndex-1),Math.min(this.chunks.length,chunkIndex+2)];
      const block=this.blocks[index];
      const domId=block?.blockId||'';
      const place=()=>{
        let target=domId?this.container.querySelector(`[data-block-id="${CSS.escape(domId)}"]`):null;
        if(!target)target=this.container.querySelector(`[data-diff-id="${CSS.escape(blockId)}"]`);
        if(target){
          const paneRect=this.container.getBoundingClientRect(),targetRect=target.getBoundingClientRect();
          this.container.scrollTop+=targetRect.top-paneRect.top-24;
        }
        return Boolean(target);
      };
      this.refresh(true,range);
      const found=place();
      // The first refresh measures the target chunks and may restore an old
      // anchor. Re-place the block after measurement so the clicked change
      // stays at the top edge instead of jumping back to the previous region.
      this.refresh(true);
      place();
      requestAnimationFrame(()=>{this.refresh(true);place();});
      return found;
    }
  }
  function virtualize(container, document, options={}){
    if(!container)return null;
    if(container._virtualDoc)container._virtualDoc.destroy();
    // Small and medium contracts fit comfortably in one chunk. Keeping every
    // paragraph mounted removes measurement jumps during linked scrolling;
    // large contracts keep the 20-block window for first-paint performance.
    const blockCount=(document.blocks||[]).length;
    if(!options.chunkSize&&blockCount&&blockCount<=400)options={...options,chunkSize:blockCount};
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
    if(state.viewMode==='classic'){state.diffPositions=null;drawLinesDeferred();}
  }
  function clearVirtual(container){if(container?._virtualDoc){container._virtualDoc.destroy();container._virtualDoc=null;}}
  function ensureDoc(side){
    if(!state.docs)state.docs={};
    if(!state.docs[side]){state.docs[side]=parseVirtualDocument(state.rawDocs?.[side]||'');state.alignment=null;}
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
    virtualize($('compare-left-pane'),ensureDoc('left'),{charsPerLine:40,collectMarks:true,onChange:onVirtualChange});
    virtualize($('compare-right-pane'),ensureDoc('right'),{charsPerLine:40,collectMarks:true,onChange:onVirtualChange});
    state.classicRendered=true;state.diffPositions=null;refreshDiffMarks();markActiveDiff();
  }
  // The result area is an inline region below the task header (chip strip
  // replaces the old fullscreen dialog: no backdrop, no Esc, no close button,
  // FL-D843).
  function setViewerOpen(open) {
    const viewer=$('compare-viewer'); if(!viewer)return;
    viewer.hidden=!open;
    // preventScroll：region 化后聚焦不再把主滚动区甩到结果区顶部，
    // 保持任务头/合同组 chip 条在视野内（FL-D843 走查发现的跳动）。
    if(open)requestAnimationFrame(()=>viewer.focus?.({preventScroll:true}));
  }
  // Pairs without a result yet (processing / failed) still open the region so
  // their status reason reads in place instead of leaving stale results of
  // the previously selected pair on screen.
  function setViewerEmpty(message) {
    const viewer=$('compare-viewer'); if(!viewer)return;
    const on=Boolean(message);
    $('compare-viewer-empty').hidden=!on;
    $('compare-viewer-empty').textContent=message||'';
    viewer.querySelectorAll('.compare-summary-row,.compare-word-toolbar,.compare-view-body').forEach(el=>{el.hidden=on;});
  }
  function renderViewer(payload) {
    state.view=payload; state.alignment=null; state.diffIndex=0; const d=payload.diffs||[]; setViewerEmpty(''); setViewerOpen(true);
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
    $('compare-revision-count-rail').textContent=String(d.length);
    const cov=payload.coverage||{}; const incomplete=cov.status!=='complete'; const warnings=cov.warnings||[];
    const chip=$('compare-coverage-chip'), chipSummary=$('compare-coverage-summary'), chipList=$('compare-coverage-list');
    if(chip&&chipSummary&&chipList){
      chip.hidden=!incomplete; chip.open=false;
      chipSummary.textContent=incomplete?`覆盖不完整 · ${warnings.length} 项未覆盖`:'';
      chipList.replaceChildren();
      if(incomplete){
        const intro=document.createElement('p'); intro.textContent='以下内容未纳入比较，请人工复核，不要据此确认全文无差异。'; chipList.append(intro);
        if(warnings.length){const ul=document.createElement('ul'); warnings.forEach(warning=>{const li=document.createElement('li');li.textContent=coverageWarningLabel(warning);ul.append(li);});chipList.append(ul);}
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
    if(state.view?.pair?.id===p.id){state.pairIndex=index;state.selectedPairId=p.id;renderPairs();setViewerOpen(true);await loadSelection(p.id);return;}
    resetSelection();const token=++state.requestToken;
    state.pairIndex=index;state.selectedPairId=p.id;state.view=null;state.classicRendered=false;state.wordSourcesRendered=false;state.diffPositions=null;state.docs=null;state.rawDocs=null;state.mergedMarks=state.wordLeftMarks=state.wordRightMarks=state.leftMarks=state.rightMarks=null;renderPairs();
    setViewerOpen(false);$('compare-lines')?.replaceChildren();for(const pane of [$('compare-word-merged-pane'),$('compare-word-left-pane'),$('compare-word-right-pane'),$('compare-left-pane'),$('compare-right-pane')]){clearVirtual(pane);if(pane)pane.innerHTML='';}
    if(!['succeeded','incomplete'].includes(p.status)){
      setViewerOpen(true); $('compare-pair-title').textContent=p.label||`第 ${index+1} 组`;
      setViewerEmpty(pairErrorLabel(p)||'该组正在处理或等待上传，暂无比对结果。');
      return;
    }
    try {const payload=await json(`/api/compare/pairs/${encodeURIComponent(p.id)}/view`);if(token===state.requestToken){p.viewError='';renderPairs();renderViewer(payload);await loadSelection(p.id);}}
    catch(e){if(token===state.requestToken){p.viewError=`读取结果失败：${e.message}`;renderPairs();}}
  }
  function schedulePoll(id){
    clearTimeout(state.poll);state.pollTaskId=id;
    // A hidden tab must not keep re-fetching the whole task every 2.5s; the
    // visibilitychange handler below schedules a refresh when it returns to
    // the foreground (B13 F7).
    if(document.visibilityState!=='visible')return;
    state.poll=setTimeout(()=>openTask(id),2500);
  }
   async function openTask(id) {
     if(api.navigate&&(api.route?.().view!=='compare'||api.route?.().mode!=='detail'||api.route?.().id!==id)){api.navigate('compare',{mode:'detail',id});return;}
     clearTimeout(state.poll);const token=++state.requestToken;
     try{const task=await json(`/api/compare/tasks/${encodeURIComponent(id)}`);if(token!==state.requestToken)return;
       const previousPairId=api.route?.().pair||state.selectedPairId;renderTask(task);
       const kept=state.pairs.findIndex(p=>p.id===previousPairId),idx=kept>=0?kept:state.pairs.findIndex(p=>['succeeded','incomplete'].includes(p.status));
       if(idx>=0){if(state.selectedPairId===state.pairs[idx]?.id&&state.view)$('compare-viewer').hidden=false;else await openPair(idx,true);}else $('compare-viewer').hidden=true;
       if(['queued','running','uploading'].includes(state.task?.status))schedulePoll(id);
     }catch(e){
       if(token!==state.requestToken)return;
       // A deep link may outlive the account that created the task. Do not
       // leave the previous identity's task and pair cards on screen.
       clearTimeout(state.poll);state.task=null;state.pairs=[];state.selectedPairId=null;state.view=null;state.docs=null;state.rawDocs=null;
       state.mergedMarks=state.wordLeftMarks=state.wordRightMarks=state.leftMarks=state.rightMarks=null;state.selection=null;state.selectionDraft=null;
       setViewerOpen(false);$('compare-detail').hidden=false;$('compare-pair-list').replaceChildren();$('compare-summary').textContent='';$('compare-revision-count-rail').textContent='0';$('compare-diff-counter').textContent='0 / 0';$('compare-diff-list').innerHTML='';$('compare-selection-downloads').replaceChildren();
       $('compare-task-name').textContent='任务不可用';
       $('compare-task-status').innerHTML=`读取任务失败：${esc(e.message)} <button class="btn btn-sm" type="button" data-compare-back-list>返回比对任务列表</button>`;
     }
   }
  function applyRoute(route){
    if(route.view!=='compare'){clearTimeout(state.poll);setViewerOpen(false);return;}
    const mode=['list','new','detail'].includes(route.mode)?route.mode:'list';$('view-compare').dataset.mode=mode;
    if(mode==='detail'&&state.task?.id!==route.id)$('compare-task-name').textContent='正在读取任务…';
    if(mode==='new'){if($('compare-create').hidden)showCreate(true);return;}
    $('compare-create').hidden=true;
    if(mode==='list'){$('compare-search').value=route.q||'';$('compare-list-filter').value=route.status||'';$('compare-detail').hidden=true;setViewerOpen(false);clearTimeout(state.poll);if(api.ready?.())loadTasks();return;}
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
    document.addEventListener('visibilitychange',()=>{
      // Resume a task poll that was suspended while the tab was hidden.
      if(document.visibilityState==='visible'&&state.pollTaskId&&['queued','running','uploading'].includes(state.task?.status))schedulePoll(state.pollTaskId);
    });
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
    document.addEventListener('click',event=>{const chip=$('compare-coverage-chip');if(chip&&chip.open&&!event.target.closest('#compare-coverage-chip'))chip.open=false;});
    $('compare-prev-diff')?.addEventListener('click',()=>focusDiff(state.diffIndex-1)); $('compare-next-diff')?.addEventListener('click',()=>focusDiff(state.diffIndex+1)); $('compare-selection-left-all')?.addEventListener('click',()=>setAllSelections('left')); $('compare-selection-right-all')?.addEventListener('click',()=>setAllSelections('right')); $('compare-selection-pending')?.addEventListener('click',()=>{const index=visibleDiffs().findIndex(item=>selectionDecision(item.id)==='pending');if(index>=0)focusDiff(index);}); $('compare-selection-save')?.addEventListener('click',()=>saveSelectionDraft()); $('compare-selection-generate')?.addEventListener('click',generateSelection); $('compare-active-only')?.addEventListener('change',drawLines); $('compare-diff-filter')?.addEventListener('change',()=>{state.diffIndex=0;renderDiffList();focusDiff(0);}); $('compare-diff-list')?.addEventListener('scroll',onDiffListScroll,{passive:true}); $('compare-retry')?.addEventListener('click',continueUploads); document.querySelectorAll('[data-word-pane]').forEach(btn=>btn.addEventListener('click',()=>setMobilePane(btn.dataset.wordPane))); $('compare-show-sources')?.addEventListener('change',e=>setSourcesVisible(e.target.checked)); $('compare-markup-mode')?.addEventListener('change',e=>setMarkupMode(e.target.value)); document.querySelectorAll('[data-compare-sources-close]').forEach(btn=>btn.addEventListener('click',()=>setSourcesVisible(false)));
      document.addEventListener('click',e=>{ const back=e.target.closest('[data-compare-back-list]');if(back){api.navigate?.('compare',{mode:'list'});return;}const task=e.target.closest('[data-compare-task]');if(task){openTask(task.dataset.compareTask);return;}const pair=e.target.closest('[data-compare-pair]');if(pair){openPair(Number(pair.dataset.comparePair));return;}const download=e.target.closest('[data-selection-download]');if(download){downloadSelection(download.dataset.selectionDownload,download.dataset.selectionFilename);return;}const diff=e.target.closest('[data-compare-diff]');if(diff&&!e.target.closest('input')){focusDiff(visibleDiffs().findIndex(x=>x.id===diff.dataset.compareDiff));return;}const mark=e.target.closest('#compare-word-merged-pane [data-diff-id],#compare-word-left-pane [data-diff-id],#compare-word-right-pane [data-diff-id],#compare-left-pane [data-diff-id],#compare-right-pane [data-diff-id]');if(mark){focusDiff(visibleDiffs().findIndex(x=>x.id===mark.dataset.diffId));return;}const remove=e.target.closest('[data-compare-remove]');if(remove){const index=Number(remove.dataset.compareRemove),row=remove.closest('.compare-pair-input');state.inputs.splice(index,1);row?.remove();if(!state.inputs.length){state.inputs=[{}];renderInputs();}else syncInputIndexes();return;} });
     document.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.matches('#compare-word-merged-pane [data-diff-id],#compare-word-left-pane [data-diff-id],#compare-word-right-pane [data-diff-id],#compare-left-pane [data-diff-id],#compare-right-pane [data-diff-id]')){e.preventDefault();focusDiff(visibleDiffs().findIndex(x=>x.id===e.target.dataset.diffId));}});
      document.addEventListener('change',e=>{const choice=e.target.closest('[data-selection-choice]');if(choice){chooseSelection(choice.dataset.diffId,choice.value);return;}const row=e.target.closest('.compare-pair-input');if(row&&e.target.matches('input[type=file]')){const i=Number(row.dataset.pairIndex),entry=state.inputs[i]||(state.inputs[i]={}),file=e.target.files?.[0]||null;entry[e.target.matches('[data-compare-left]')?'_left':'_right']=file;row.querySelector('.compare-file-label').textContent=[entry._left?.name,entry._right?.name].filter(Boolean).join(' / ')||'尚未选择文件';
        // FL-D859: 选择文件后同步更新卡片文件名、has-file 态与按钮文案，
        // 原实现只更新 sr-only 摘要，用户无法确认选择成功。
        const card=e.target.closest('.compare-file-card');
        if(card){const name=file?fileName(file):'';card.classList.toggle('has-file',!!name);const nameEl=card.querySelector('.compare-file-name');if(nameEl){nameEl.textContent=name||'尚未选择合同';nameEl.title=name;}const btn=card.querySelector('[data-compare-choose]');if(btn)btn.textContent=name?'更换文件':'选择文件';}
        return;}if(e.target.id==='compare-left-folder'||e.target.id==='compare-right-folder'){const side=e.target.id.includes('left')?'left':'right';state[`folder${side[0].toUpperCase()+side.slice(1)}`]=[...e.target.files].filter(f=>fileName(f).toLowerCase().endsWith('.docx')).sort((a,b)=>relativePath(a).localeCompare(relativePath(b)));const other=side==='left'?state.folderRight:state.folderLeft;if(!other?.length)return;const left=state.folderLeft||[],right=state.folderRight||[],map=new Map(right.map(f=>[relativePath(f),f])),used=new Set(),entries=left.map(f=>{const r=map.get(relativePath(f));if(r)used.add(r);return {_left:f,_right:r||null};});for(const f of right)if(!used.has(f))entries.push({_left:null,_right:f});state.inputs=entries;renderInputs();$('compare-upload-message').textContent=`已按相对路径配对 ${entries.filter(x=>x._left&&x._right).length} 组；${entries.filter(x=>!x._left||!x._right).length} 个文件未配对，可手工补齐。`;}});
     bindCompareSplitter();
    bindPanelSplitters();
      for(const pane of allPanels()){
        pane?.addEventListener('scroll',()=>syncPaneScroll(pane),{passive:true});
        const takeControl=()=>{clearTimeout(state.syncSettle);state.syncTargets.clear();};
        for(const event of ['wheel','pointerdown','touchstart'])pane?.addEventListener(event,takeControl,{passive:true});
      }
      window.addEventListener('resize',()=>{state.diffPositions=null;refreshVirtualLayouts();drawLines();setTimeout(alignPanels,160);});
      const body=$('compare-view-body'); if(body&&window.ResizeObserver)new ResizeObserver(drawLines).observe(body);
      document.querySelectorAll('[data-compare-view-mode]').forEach(button=>button.addEventListener('click',()=>setViewMode(button.dataset.compareViewMode)));
      document.querySelectorAll('#compare-classic-view [data-compare-side]').forEach(button=>button.addEventListener('click',()=>setClassicSide(button.dataset.compareSide)));
      try { const storedSources=localStorage.getItem('fundlex-compare-show-sources'); setSourcesVisible(storedSources==='1',false); const storedMarkup=localStorage.getItem('fundlex-compare-markup'); if(storedMarkup)setMarkupMode(storedMarkup,false); const storedPane=localStorage.getItem('fundlex-compare-mobile-pane'); if(storedPane)setMobilePane(storedPane,false); const storedMode=localStorage.getItem('fundlex-compare-view-mode'); if(storedMode)setViewMode(storedMode,false); const storedSide=localStorage.getItem('fundlex-compare-classic-side'); if(storedSide)setClassicSide(storedSide,false); } catch {}
      document.addEventListener('fundlex:view',e=>{if(e.detail==='compare'){drawLines();}}); document.addEventListener('fundlex:identity-reset',()=>{clearTimeout(state.poll);state.identityToken++;state.listToken++;state.tasks=[];state.task=null;state.pairs=[];state.selectedPairId=null;state.view=null;state.mergedMarks=state.wordLeftMarks=state.wordRightMarks=state.leftMarks=state.rightMarks=null;state.selection=null;state.selectionDraft=null;state.selectionDirty=false;state.uploadDraft=null;state.inputs=[{}];state.requestToken++;state.selectionToken++;resetFolders();$('compare-create').hidden=true;$('compare-submit').disabled=false;$('compare-retry').hidden=true;$('compare-upload-message').textContent='';$('compare-name').value='';$('compare-detail').hidden=true;setViewerOpen(false);for(const pane of [$('compare-word-merged-pane'),$('compare-word-left-pane'),$('compare-word-right-pane'),$('compare-left-pane'),$('compare-right-pane')]){clearVirtual(pane);if(pane)pane.innerHTML='';}$('compare-diff-list').innerHTML='';$('compare-selection-downloads').replaceChildren();selectionStatus('');$('compare-lines')?.replaceChildren();$('compare-diff-counter').textContent='0 / 0';$('compare-revision-count-rail').textContent='0';renderInputs();renderTasks();}); state.inputs=[{}];renderInputs();applyRoute(api.route?.()||{view:'compare',mode:'list'});
  }
  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded',bind); else bind();
})();
