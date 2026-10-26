(() => {
  'use strict';
  const api=window.FundLexWorkbench,$=id=>document.getElementById(id),esc=api.esc;
  const kinds={revision:'合同修改',compare:'合同比对',generation:'指引生成'};
  const phases={uploading:'等待上传',queued:'排队中',running:'处理中',leased:'处理中',paused:'已暂停',retry_wait:'等待重试',completed:'处理结束',complete:'处理结束',complete_with_unresolved:'含待处理问题',failed:'处理失败',INGEST_REGULATION:'读取法规',EXTRACT_REQUIREMENTS:'提取法规要求',VERIFY_REQUIREMENTS:'核验法规要求',BUILD_CORPUS_SNAPSHOT:'准备合同语料',DISCOVER_IMPACTS:'分析合同影响',AUTHOR_GUIDE:'起草候选指引',QUALITY_REVIEW:'质量核验',COVERAGE_REVIEW:'覆盖核验',RESIDUAL_MINING:'查漏与补充',FINALIZE_GUIDE:'整理候选指引',BUILD_EVIDENCE:'生成证据报告'};
  let route={},token=0,timer=null,busy=false;
  function navigate(values){api.navigate('workspace',{...route,...values});}
  function time(value){if(!value)return '—';const d=new Date(typeof value==='number'?value*1000:value);return Number.isNaN(d.getTime())?'—':d.toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});}
  function setInputs(){
    $('workspace-search').value=route.q||'';$('workspace-status').value=route.status||'';$('workspace-sort').value=route.sort||'updated_desc';
    $('workspace-date-from').value=route.date_from||'';$('workspace-date-to').value=route.date_to||'';
    document.querySelectorAll('[data-workspace-kind]').forEach(n=>{const active=n.dataset.workspaceKind===(route.kind||'');n.classList.toggle('is-active',active);n.setAttribute('aria-pressed',String(active));});
    document.querySelectorAll('[data-workspace-status]').forEach(n=>n.classList.toggle('is-active',n.dataset.workspaceStatus===route.status));
  }
  async function load(){
    if(!api.ready()||!api.authenticated()||api.view()!=='workspace')return;
    const current=++token,epoch=api.epoch();busy=true;
    $('workspace-state').textContent='正在读取全部业务任务…';$('workspace-task-rows').setAttribute('aria-busy','true');
    try{
      const params=new URLSearchParams({...route,page:route.page||'1',page_size:'20'});params.delete('view');
      const data=await api.json(`/api/workspace/tasks?${params}`);
      if(current!==token||epoch!==api.epoch()||api.view()!=='workspace')return;
      const stats=data.stats||{};
      $('workspace-active').textContent=stats.active??'—';$('workspace-attention').textContent=stats.attention??'—';$('workspace-completed').textContent=stats.recent_completed??'—';
      $('workspace-state').textContent=`共 ${data.total} 个匹配任务 · 统计卡片按本账号全部业务计算，数量之间可重叠`;
      $('workspace-task-rows').innerHTML=(data.items||[]).map(item=>{
        const notes=Array.isArray(item.attention)?item.attention:[];
        const attention=notes.map(n=>typeof n==='string'?n:n.label||n.code).filter(Boolean).join('；');
        const status=item.status_label||phases[item.status]||'查看任务状态';
        const phase=item.phase_label||phases[item.phase]||status;
        return `<tr><td><strong class="workspace-task-name">${esc(item.name)}</strong><small class="row-sub">创建于 ${esc(time(item.created_at))}</small></td><td><span class="business-type is-${esc(item.kind)}">${esc(kinds[item.kind]||item.kind)}</span></td><td>${esc(item.scale?.value??'—')} ${esc(item.scale?.unit||'')}</td><td><span>${esc(status)}</span>${phase!==status?`<small class="row-sub">${esc(phase)}</small>`:''}</td><td class="workspace-attention-cell">${attention?`<span class="workspace-attention-text">${esc(attention)}</span>`:'<span class="subnote">暂无额外待办，交付情况请查看详情</span>'}</td><td class="workspace-time">${esc(time(item.updated_at))}</td><td><button type="button" class="btn-link" data-workspace-open="${esc(item.kind)}" data-id="${esc(item.id)}">进入任务</button></td></tr>`;
      }).join('')||'<tr><td colspan="7"><div class="empty"><strong>当前条件下没有任务</strong><p>选择上方业务入口开始，或调整搜索和筛选条件。</p></div></td></tr>';
      const page=Number(data.page)||1,max=Math.max(1,Math.ceil(data.total/(data.page_size||20)));
      $('workspace-pagination').innerHTML=`<span>第 ${page} / ${max} 页 · ${data.total} 个任务</span><button type="button" class="btn btn-sm" data-workspace-page="${page-1}" ${page<=1?'disabled':''}>上一页</button><button type="button" class="btn btn-sm" data-workspace-page="${page+1}" ${page>=max?'disabled':''}>下一页</button>`;
    }catch(error){
      if(current!==token||epoch!==api.epoch()||error.name==='AbortError')return;
      $('workspace-state').textContent='任务暂时无法读取，请点击刷新重试。';
      $('workspace-task-rows').innerHTML='<tr><td colspan="7"><div class="empty">无法读取任务；未将错误结果当作空任务。</div></td></tr>';
      $('workspace-pagination').replaceChildren();for(const id of ['active','attention','completed'])$(`workspace-${id}`).textContent='—';
    }finally{if(current===token){busy=false;$('workspace-task-rows').removeAttribute('aria-busy');}}
  }
  function openTask(kind,id){if(kind==='revision')api.navigate('task',{id});else api.navigate(kind==='generation'?'generation':'compare',{mode:'detail',id});}
  document.addEventListener('click',e=>{
    const fresh=e.target.closest('[data-workspace-new]');if(fresh){api.navigate(fresh.dataset.workspaceNew,{mode:'new'});return;}
    const kind=e.target.closest('[data-workspace-kind]');if(kind){navigate({kind:kind.dataset.workspaceKind,page:'1'});return;}
    const status=e.target.closest('[data-workspace-status]');if(status){navigate({status:status.dataset.workspaceStatus,page:'1'});return;}
    const page=e.target.closest('[data-workspace-page]');if(page){navigate({page:page.dataset.workspacePage});return;}
    const task=e.target.closest('[data-workspace-open]');if(task)openTask(task.dataset.workspaceOpen,task.dataset.id);
  });
  $('workspace-refresh').addEventListener('click',load);
  $('workspace-search').addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(()=>navigate({q:$('workspace-search').value.trim(),page:'1'}),300);});
  for(const [id,key] of [['workspace-status','status'],['workspace-sort','sort'],['workspace-date-from','date_from'],['workspace-date-to','date_to']])$(id).addEventListener('change',()=>navigate({[key]:$(id).value,page:'1'}));
  document.addEventListener('fundlex:route',e=>{if(e.detail.view!=='workspace'){token++;busy=false;clearTimeout(timer);return;}route={...e.detail};delete route.view;setInputs();load();});
  document.addEventListener('fundlex:identity-reset',()=>{token++;busy=false;route={};clearTimeout(timer);$('workspace-task-rows').replaceChildren();$('workspace-pagination').replaceChildren();$('workspace-state').textContent='';for(const id of ['active','attention','completed'])$(`workspace-${id}`).textContent='—';setInputs();});
  setInterval(()=>{if(!busy&&document.visibilityState==='visible'&&api.view()==='workspace'&&document.activeElement?.id!=='workspace-search')load();},15000);
  if(api.route()?.view==='workspace'){route=api.route();setInputs();load();}
})();
