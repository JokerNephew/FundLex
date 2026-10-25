(() => {
  'use strict';
  const APP_BASE_PATH = location.pathname === '/test' || location.pathname.startsWith('/test/') ? '/test' : '';
  const appPath = path => `${APP_BASE_PATH}${path}`;
  const $ = id => document.getElementById(id), MiB = 1024 * 1024;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const size = n => n >= MiB ? `${(n / MiB).toFixed(1)} MiB` : `${Math.ceil(n / 1024)} KiB`;
  const labels = {uploading:'上传中',queued:'排队中',running:'处理中',leased:'处理中',retry_wait:'等待重试',paused:'已暂停',completed:'处理完成',succeeded:'已处理',failed:'失败关闭',eligible:'资格符合',excluded_by_fund_type:'已排除',pending:'未判定',complete:'产物完整',incomplete:'结果不完整',not_generated:'未生成',accepted:'已上传',rejected:'接收失败',not_started:'尚未接收',partial:'部分上传',sealed_incomplete:'上传未完成',applied:'已修改',satisfied:'已符合',satisfied_no_change:'已符合',not_applicable:'不适用',not_matched:'未命中',needs_edit:'待修改',planned:'已规划',unresolved:'未完成',excluded:'已排除',unknown:'未确认',evaluation_modified:'已修改（评测）',evaluation_unmodified:'无需修改（评测）',evaluation_modified_with_exceptions:'已修改（含例外，评测）',complete:'产物完整',complete_with_exceptions:'已交付（含例外条款）',uploaded:'待解析',parsing:'解析中',parsed:'已解析',validated:'已校验',parse_failed:'解析失败',released:'已发布',archived:'已归档'};
  const reasons = {
    FUND_TYPE_EVIDENCE_AMBIGUOUS:'基金类型证据不明确，已保守停止该合同', FUND_TYPE_UNKNOWN:'无法确定基金类型，已保守停止该合同', EXISTING_REVISION_UNSUPPORTED:'源合同含已有修订痕迹，无法安全处理',
    DOCUMENT_IDENTITY_EVIDENCE_MISSING:'缺少可核验的基金合同身份依据，已停止处理', NON_CONTRACT_DOCUMENT:'文档未被确认为基金合同，已停止处理', DOCUMENT_TYPE_CONFLICT:'文档类型依据互相冲突，已停止处理',
    FUND_TYPE_EVIDENCE_MISSING:'缺少明确的基金类型依据，已停止处理', FUND_TYPE_EVIDENCE_INVALID:'基金类型引用未通过原文核验，已停止处理', FUND_TYPE_INVESTMENT_EVIDENCE_MISSING:'缺少可核验的投资范围依据，已停止处理', FUND_TYPE_INVESTMENT_EVIDENCE_CONFLICT:'基金类型与投资范围依据冲突，已停止处理', FUND_TYPE_OPERATION_EVIDENCE_INVALID:'运作方式依据未通过核验，已停止处理', FUND_TYPE_CD_MANDATE_EVIDENCE_MISSING:'缺少同业存单投资约定依据，已停止处理', QUALIFICATION_CONTEXT_LIMIT:'资格判断所需文本超出支持范围，已停止处理',
    MODEL_TYPE_CONFLICT:'模型判断与合同类型依据不一致，已停止处理', MODEL_EVIDENCE_INVALID:'模型引用未通过合同原文核验', MODEL_QUOTE_MISMATCH:'处理结果引用与合同原文不一致', MODEL_CONFIG_MISSING:'模型处理服务尚未配置', MODEL_HTTP_ERROR:'模型服务返回异常，未生成可用结果', MODEL_CONTEXT_LIMIT:'处理文本超出支持范围', MODEL_RESPONSE_LIMIT:'处理结果超过接收限制', MODEL_CHECKPOINT_UNAVAILABLE:'处理检查点暂不可用，任务已暂停保护',
    PROFILE_CLASS_SET_CONFLICT:'份额类别依据互相冲突，相关动作未执行', PROFILE_CLASS_NAME_EVIDENCE_MISSING:'缺少份额类别名称依据，相关动作未执行', PROFILE_EVIDENCE_INVALID:'份额或收费引用未通过原文核验', PROFILE_FEE_POLARITY_UNVERIFIED:'无法确认相关费用是否收取，相关动作未执行', PROFILE_MANAGEMENT_FEE_CONFLICT:'管理费依据互相冲突，相关动作未执行', RULE_CONDITION_UNKNOWN:'无法确认规则适用条件，未自动修改',
    DOCUMENT_PROTECTED:'合同设置了编辑保护，无法安全处理', SIGNED_OR_MACRO_UNSUPPORTED:'合同包含签名或宏结构，无法安全处理', STRICT_OOXML_UNSUPPORTED:'该 DOCX 格式版本暂不支持安全处理', ZIP_INVALID:'DOCX 文件包损坏或格式异常', XML_INVALID:'DOCX 内部内容格式异常', INPUT_INTEGRITY_FAILED:'源文件完整性校验失败，已停止处理', ENGINE_SCHEMA_MISMATCH:'处理引擎版本已变化，请按当前版本新建任务', RULESET_HASH_MISMATCH:'规则包内容已变化，请按当前规则新建任务', MISSING_VERIFIED_ARTIFACTS:'合同产物未通过完整交付校验，未开放下载', ARTIFACT_VERIFICATION_MISMATCH:'合同产物完整性校验失败，未开放下载', OUTPUT_IO_ERROR:'处理文件写入失败，未生成可用结果', PROCESSING_FAILED:'合同处理发生异常，已隔离该合同',
    MODEL_SCHEMA_INVALID:'处理结果格式未通过校验', MODEL_EVIDENCE_UNKNOWN:'处理结果引用的证据无法核验', PROFILE_EVIDENCE_INCOMPLETE:'份额与收费证据不完整',
    ACTION_RELEASE_GATE_CLOSED:'规则动作尚未开放自动写入', RELEASE_GATE_CLOSED:'规则动作尚未开放自动写入', TARGET_SCOPE_UNRESOLVED:'无法确定条款适用范围，未自动修改', UNSUPPORTED_TARGET_STRUCTURE:'条款结构暂不支持安全修改', LOCAL_TARGET_VERIFICATION_REQUIRED:'条款位置需要进一步校验，未自动修改',
    V2_ALREADY_SATISFIED:'原合同已符合要求，无需修改', V2_TARGET_NOT_LOCATED:'未能在合同中准确定位该条款，保持原文', V2_TARGET_AMBIGUOUS:'条款位置不唯一，按安全规则保持原文', V2_CLASS_DEFINITION_CONFLICT:'份额类别与收费信息不一致，保持原文', V2_HYBRID_CLASS_FEE_UNSUPPORTED:'存在同时收两种费用的类别，无法安全套用统一规则', V2_EXISTING_CLAUSE_UNSUPPORTED:'该段已包含部分直销条款，为避免重复保持原文',
    V2_SLOT_UNRESOLVED:'类别收费分组证据不足，规则文案无法按实际类别生成，保持原文', V2_SCOPE_TEXT_MISMATCH:'整句或整段与规则指引旧文不一致，为避免丢字保持原文', V2_DELIVERY_REQUIRES_RELEASED_PACKAGE:'规则包尚未发布，拒绝正式写入', V2_RELEASE_CONTEXT_UNVERIFIED:'引擎或模型配置与发布证据不一致，已停止写入，请重新发布', V2_RELEASE_NOT_SEPARATE:'未发布的规则包不能开启自动写入', V2_RELEASE_EVIDENCE_MISSING:'发布证据不完整，拒绝开启自动写入', V2_RELEASE_METRIC_BELOW_THRESHOLD:'发布指标未达预注册门槛，拒绝开启自动写入',
    V2_FACT_ROLE_MISMATCH:'改写依据无法对应到合同原文，按安全规则保持原文', V2_FACT_INCOMPLETE:'改写依据不完整，保持原文', V2_FACT_ROLE_INVALID:'改写依据来源无效，保持原文', V2_VERIFY_NOT_SATISFIED:'独立复核认为改写未完全满足要求，保持原文', V2_VERIFY_QUOTE_MISMATCH:'独立复核引用无法核对，保持原文', V2_CONTENT_CHECK_FAILED:'改写内容未通过规则校验，保持原文', V2_REPLACEMENT_INVALID:'改写内容格式不符合要求，保持原文', V2_REPLACEMENT_UNCHANGED:'改写内容与原文相同，无需修改', V2_SOURCE_QUOTE_MISMATCH:'模型定位与系统记录不一致，保持原文', V2_JOIN_UNSAFE:'改写内容与原文衔接未通过校验，保持原文', V2_ACTION_PARTIAL_REVERTED:'同一动作存在未完成目标，整组保持原文', V2_BODY_SUMMARY_CONFLICT:'正文与摘要改写不一致，整组保持原文', V2_LOCATE_SCOPE_TOO_WIDE:'候选条款范围过宽，按安全规则保持原文', CROSS_PARAGRAPH_TARGET_UNSUPPORTED:'目标内容跨段落，暂不支持安全修改', SHORT_HOLDING_NON_TARGET_HOST:'该句属于费用归属条款，由另一项规则处理',
    MODEL_NETWORK_ERROR:'模型服务连接暂时失败', MODEL_RETRY_EXHAUSTED:'模型服务重试后仍未成功', MODEL_CIRCUIT_OPEN:'模型服务连续异常，任务已暂停保护', MODEL_GLOBAL_CALL_BUDGET_EXCEEDED:'累计调用额度已用完，任务已暂停', MODEL_CALL_BUDGET_EXCEEDED:'调用额度已用完，任务已暂停', MODEL_COST_BUDGET_EXCEEDED:'费用上限已达到，任务已暂停', MODEL_LEDGER_UNAVAILABLE:'调用费用记录暂不可用，任务已暂停', MODEL_NOT_CONFIGURED:'处理服务尚未配置', WORKER_ATTEMPTS_EXHAUSTED:'处理重试次数已达上限', TEMPORARY_STORAGE_FAILURE:'文件存储暂时异常',
    INVALID_DOCX:'文件不是有效的可编辑 DOCX', DOCX_INVALID:'文件不是有效的可编辑 DOCX', UPLOAD_TOO_LARGE:'文件超过接收大小限制', UNSUPPORTED_FORMAT:'文件格式不受支持，仅接收 DOCX', DOCUMENT_VALIDATION_FAILED:'DOCX 内容校验未通过', UPLOAD_REJECTED:'文件接收校验未通过', UNSUPPORTED_FILE_FORMAT:'仅接收可编辑 DOCX 文件', UPLOAD_SIZE_LIMIT:'文件超过接收大小限制', DUPLICATE_DOCX_MEMBER:'DOCX 内部存在重复文件条目，无法安全接收', DOCX_PART_SIZE_LIMIT:'DOCX 内部内容超过大小限制', DOCX_COMPRESSION_RATIO_LIMIT:'DOCX 压缩结构超出安全接收限制', DOCX_EXPANDED_SIZE_LIMIT:'DOCX 解压内容超过安全接收限制', UPLOAD_REQUEST_SIZE_LIMIT:'本次文件接收超出限制，请重新补传', MANIFEST_ENTRY_NOT_FOUND:'文件未包含在原任务清单中', MANIFEST_FILE_MISMATCH:'本地文件与原任务清单不匹配，请重新选择', UPLOAD_IDENTITY_CONFLICT:'文件身份发生冲突，请确认源文件后重试',
    DOCX_VALIDATION_FAILED:'DOCX 文件内容或结构校验未通过', INVALID_DOCX_PACKAGE:'文件不是有效的可编辑 DOCX', ENCRYPTED_DOCX:'文件已加密，无法安全处理', DOCX_SIZE_LIMIT_EXCEEDED:'文件超过接收大小限制', DOCX_UNSUPPORTED:'DOCX 结构不受支持', DOCX_SECURITY_LIMIT:'DOCX 解压校验超出安全限制',
    GUIDE_NOT_READY:'当前指引不可用或尚未解析完成，请先在「指引配置」启用可用指引', GUIDE_NOT_ENABLEABLE:'该指引尚未解析完成，暂不能启用', GUIDE_NOT_PARSEABLE:'当前状态不能重新解析', GUIDE_PARSE_FAILED:'指引解析未完成，可查看问题后重新解析', GUIDE_DOCUMENT_INVALID:'指引文档未通过解析校验', ENGINE_OR_RULESET_REQUIRED:'提交缺少引擎或规则信息，请刷新后重试', ENGINE_CONFLICT:'引擎与规则信息冲突，请刷新后重试', ENGINE_UNSUPPORTED:'当前环境不支持所选引擎', BUILTIN_SOURCE_UNAVAILABLE:'内置指引不提供原件下载'
  };
  const reason = code => reasons[code] || (code ? '处理未安全完成，请稍后重试或联系管理员' : '');
  const badge = (value, override) => `<span class="badge b-${['eligible','succeeded','completed','complete','accepted','satisfied','satisfied_no_change','evaluation_modified','evaluation_unmodified','parsed','released','validated'].includes(value)?'green':['failed','rejected','incomplete','parse_failed'].includes(value)?'red':['running','queued','leased','uploading','parsing'].includes(value)?'blue':['paused','excluded_by_fund_type','retry_wait'].includes(value)?'amber':'gray'}">${esc(override || labels[value] || '未确认')}</span>`;
  const state = {view:'overview',epoch:0,controllers:new Set(),tokens:{},tasks:[],selected:null,task:null,cap:null,tasksLoaded:false,guideDismissed:false,imports:[],recover:null,uploading:false,uploadToken:null,createKey:null,taskPage:1,importPage:1,docPage:1,taskSize:20,importSize:20,docSize:20,taskDocs:[],detail:null,focusReturn:null,guides:null,guidesFailed:false,guideBusy:null,guideUploading:false,guideTimer:null,guideDetail:null,auth:{mode:'dev',loginRequired:false,registrationOpen:false,token:'',user:null},review:null,reviewDocs:null,reviewDocsTask:null,reviewDocsKey:'',reviewDecisions:new Map(),uploadProgress:null,replaceTarget:null,toastSeq:0,importSession:0,refreshBusy:false,overviewStats:null,taskGuides:null};
  const notifications=[];let taskStatuses=new Map(),notificationBusy=false;
  function renderNotifications(){const unread=notifications.filter(n=>!n.read).length;$('notification-count').textContent=unread||'';$('notification-count').hidden=!unread;$('notification-toggle').setAttribute('aria-label',unread?`消息，${unread} 条未读`:'消息');$('notification-list').innerHTML=notifications.length?notifications.map(n=>`<li><p>${esc(n.message)}</p>${n.taskId?`<button class="btn-link" data-task="${esc(n.taskId)}">查看任务</button>`:''}<time>${esc(new Date(n.time).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'}))}</time></li>`).join(''):'<li>暂无重要消息</li>';}
  function notify(message,error=false,taskId=null){if(!message)return;const recent=notifications.find(n=>n.message===message&&n.taskId===taskId&&Date.now()-n.time<60000);if(recent)return;notifications.unshift({message,error,taskId,time:Date.now(),read:false});notifications.splice(50);renderNotifications();}
  // 错误同时进入铃铛与全局提示；成功类操作只做全局轻提示。
  function notice(message,error=false){if(error)toast(message,true);}
  const BASE_TITLE='FundLex合同修订工作台';
  function showToast(message,kind='success'){
    const el=$('toast');if(!el||!message)return;
    const now=Date.now(),key=kind+'|'+String(message);
    showToast.recent=showToast.recent||{};
    if(showToast.recent[key]&&now-showToast.recent[key]<8000)return;
    showToast.recent[key]=now;
    el.hidden=false;
    const item=document.createElement('div');item.className=`toast-item ${kind}`;item.setAttribute('role',kind==='error'?'alert':'status');
    item.innerHTML=`<span class="toast-text">${esc(message)}</span><button type="button" class="toast-close" aria-label="关闭提示">×</button>`;
    item.querySelector('.toast-close').addEventListener('click',()=>{item.remove();if(!el.children.length)el.hidden=true;});
    el.append(item);
    while(el.children.length>4)el.firstElementChild.remove();
    setTimeout(()=>{item.remove();if(!el.children.length)el.hidden=true;},kind==='error'?9000:4200);
  }
  function toast(message,error=false){if(!message)return;const kind=error===true?'error':typeof error==='string'?error:'success';if(kind==='error')notify(message,true);showToast(message,kind);}
  function flash(message){toast(message,'success');}
  async function monitorTasks(){if(notificationBusy||!state.cap||(state.auth.mode==='password'&&!state.auth.token))return;notificationBusy=true;const epoch=state.epoch;try{let page=1,total=Infinity,seen=0;const next=new Map();while(seen<total){const p=await json(`/api/tasks?page=${page++}&page_size=200`);if(!identityCurrent(epoch))return;for(const t of p.items){next.set(t.id,t.status);const old=taskStatuses.get(t.id);if(old&&old!==t.status&&['completed','paused'].includes(t.status))notify(`${t.name}：${t.status==='completed'?'处理结束，可查看结果':'任务已暂停，请查看原因'}`,t.status==='paused',t.id);}seen+=p.items.length;total=p.total;if(!p.items.length)break;}taskStatuses=next;}catch(e){if(identityCurrent(epoch))errorNotice(e);}finally{notificationBusy=false;}}
  function owner() { return $('dev-user').value.trim(); }
  const identityCurrent = epoch => epoch===state.epoch;
  const AUTH_TOKEN_KEY='fundlex-auth-token',AUTH_USER_KEY='fundlex-auth-user';
  function storedToken(){try{return sessionStorage.getItem(AUTH_TOKEN_KEY) || '';}catch{return '';}}
  function storedUser(){try{const raw=sessionStorage.getItem(AUTH_USER_KEY);return raw?JSON.parse(raw):null;}catch{return null;}}
  function setAuthSession(token,user){state.auth.token=token || '';state.auth.user=user || null;try{if(token)sessionStorage.setItem(AUTH_TOKEN_KEY,token);else sessionStorage.removeItem(AUTH_TOKEN_KEY);if(user)sessionStorage.setItem(AUTH_USER_KEY,JSON.stringify(user));else sessionStorage.removeItem(AUTH_USER_KEY);}catch{}renderAuthUI();}
  function clearAuthSession(){setAuthSession('',null);}
  function renderAuthUI(){const box=$('topbar-user');if(!box)return;const user=state.auth.user;const active=state.auth.mode==='password'&&!!user;box.hidden=!active;if(active)$('topbar-username').textContent=user.display_name||user.username||'已登录';updateSettingsNav();updateUsersNav();updateGuideNav();}
  function updateSettingsNav(){const btn=document.querySelector('.sidebar [data-nav="settings"]');if(!btn)return;const hide=state.auth.mode==='password';btn.hidden=hide;if(hide&&state.view==='settings')go('overview');}
  function updateUsersNav(){const btn=$('nav-users');if(!btn)return;const show=state.auth.mode==='password'&&!!state.auth.user&&state.auth.user.role==='admin';btn.hidden=!show;if(!show&&state.view==='users')go('overview');}
  function updateGuideNav(){const btn=document.querySelector('.sidebar [data-nav="guide"]');if(!btn)return;const show=state.auth.mode!=='password'||!!state.auth.user;btn.hidden=!show;if(!show&&state.view==='guide')go('overview');}
  function showLogin(message){const view=$('login-view');if(!view)return;const wasHidden=view.hidden;view.hidden=false;const app=document.querySelector('.app');if(app)app.inert=true;const hint=$('register-hint');if(hint)hint.hidden=!(state.auth.mode==='password'&&state.auth.registrationOpen);const box=$('login-error');box.textContent=message || '';box.hidden=!message;if(wasHidden){switchAuthMode('login');box.hidden=!message;(($('login-username').value)?$('login-password'):$('login-username')).focus();}}
  function switchAuthMode(mode){const login=$('login-form'),register=$('register-form');if(!login||!register)return;const showRegister=mode==='register';login.hidden=showRegister;register.hidden=!showRegister;if(showRegister){$('register-error').hidden=true;$('register-username').focus();}else{$('login-error').hidden=true;$('login-username').focus();}}
  function hideLogin(){const view=$('login-view');if(!view||view.hidden)return;view.hidden=true;$('login-password').value='';const app=document.querySelector('.app');if(app)app.inert=false;}
  function ticket(scope) { const token=(state.tokens[scope] || 0)+1; state.tokens[scope]=token; return {epoch:state.epoch,token,scope}; }
  function current(t) { return identityCurrent(t.epoch) && state.tokens[t.scope]===t.token; }
  function stale() { return new DOMException('请求已被新的操作替代','AbortError'); }
  async function api(path,options={}) {
    const epoch=state.epoch,identity=owner(),token=state.auth.token; if(!identity&&!token&&state.auth.mode!=='password'&&path!=='/api/capabilities')throw new Error('请在开发设置中填写本地开发身份。');
    if(!path.startsWith('/api/') || path.startsWith('//'))throw new Error('服务端返回了不支持的下载路径。');
    const controller=new AbortController();state.controllers.add(controller);const headers=new Headers(options.headers || {}); if(token)headers.set('Authorization',`Bearer ${token}`); if(identity)headers.set('X-FundLex-User',identity);
    try { let response;try{response=await fetch(appPath(path),{...options,headers,signal:controller.signal,cache:'no-store'});}catch(error){if(!identityCurrent(epoch))throw stale();if(error&&error.name==='AbortError')throw error;const offline=new Error('无法连接本地服务，请确认服务已启动，然后重试。');offline.code='CONNECTION';throw offline;} if(!identityCurrent(epoch))throw stale();
      if(response.status===401&&state.auth.mode==='password'){handleSessionExpired();const expired=new Error('登录状态已失效，请重新登录。');expired.code=401;throw expired;}
      if(!response.ok) { let detail=''; try { const p=await response.json();detail=typeof p.detail==='string'?p.detail:JSON.stringify(p.detail || p); } catch { detail=response.statusText; }
        if(!identityCurrent(epoch))throw stale(); const messages={401:'开发身份无效，请检查开发设置。',403:'没有访问此结果的权限。',404:'该任务或结果不存在，或当前身份无权访问。',503:'服务暂不可用；生产身份服务尚未配置时将关闭访问。',413:'文件超过接收限制，请检查文件大小。',409:'任务状态已变化或请求存在冲突，请刷新后重试。'};
        const error=new Error(reasons[detail] || messages[response.status] || reason(detail) || '请求未完成，请稍后重试。');error.code=response.status;error.raw=detail;throw error;
      } return {response,epoch};
    } finally {state.controllers.delete(controller);}
  }
  async function json(path,options) { const {response,epoch}=await api(path,options);const payload=await response.json();if(!identityCurrent(epoch))throw stale();return payload; }
  function uploadRequest(path,form,onProgress) {
    const epoch=state.epoch,identity=owner(),token=state.auth.token;
    return new Promise((resolve,reject)=>{
      if(!identity&&!token){reject(new Error('请填写本地开发身份。'));return;}
      const xhr=new XMLHttpRequest();state.controllers.add(xhr);
      const finish=()=>state.controllers.delete(xhr);
      xhr.open('POST',appPath(path));if(identity)xhr.setRequestHeader('X-FundLex-User',identity);if(token)xhr.setRequestHeader('Authorization',`Bearer ${token}`);
      xhr.upload.onprogress=e=>{if(identityCurrent(epoch)&&e.lengthComputable)onProgress(e.loaded,e.total);};
      xhr.onabort=()=>{finish();reject(stale());};
      xhr.onerror=()=>{finish();reject(new Error('网络连接中断，已接收文件保留，可重新补传。'));};
      xhr.onload=()=>{finish();if(!identityCurrent(epoch)){reject(stale());return;}
        if(xhr.status===401&&state.auth.mode==='password'){handleSessionExpired();const expired=new Error('登录状态已失效，请重新登录。');expired.code=401;reject(expired);return;}
        let payload;try{payload=JSON.parse(xhr.responseText);}catch{reject(new Error('服务响应未通过格式校验，请刷新任务后补传。'));return;}
        if(xhr.status>=200&&xhr.status<300){resolve(payload);return;}
        const error=new Error(xhr.status===404?'任务不存在或当前身份无权访问。':xhr.status===413?'本次文件接收超出限制，请检查文件后补传。':reason(payload.detail)||'文件接收未完成，请刷新任务后补传。');error.raw=payload.detail;error.code=xhr.status;reject(error);
      };
      xhr.send(form);
    });
  }
  function errorNotice(error,prefix=''){if(error.name!=='AbortError')toast(prefix+error.message,true);}
  function param(values) { const p=new URLSearchParams();for(const [k,v] of Object.entries(values))if(v!==''&&v!=null)p.set(k,v);return p.toString(); }
  function pathTask(id=state.selected) { return `/api/tasks/${encodeURIComponent(id)}`; }
  function pathDoc(doc) { return `/api/batches/${encodeURIComponent(doc.batch_id)}/documents/${encodeURIComponent(doc.document_id)}`; }
  function emptyRow(cols,message) {return `<tr><td colspan="${cols}"><div class="empty"><strong>${esc(message)}</strong></div></td></tr>`;}
  function pagination(name,total,page,pageSize) {const pages=Math.max(1,Math.ceil(total/pageSize));return `<span>共 ${total} 条 · 第 ${page} / ${pages} 页</span><div class="controls"><label for="${name}-page-size">每页</label><select id="${name}-page-size" data-pagesize="${name}">${[10,20,50,100].map(n=>`<option value="${n}" ${n===pageSize?'selected':''}>${n}</option>`).join('')}</select><button class="btn btn-sm" data-page="${name}" data-dir="prev" ${page<=1?'disabled':''}>上一页</button><button class="btn btn-sm" data-page="${name}" data-dir="next" ${page>=pages?'disabled':''}>下一页</button></div>`;}
  const FILTER_DEFAULTS={task:{q:'',status:'',guide_version_id:'',sort:'newest'},doc:{q:'',upload_status:'',eligibility:'',job_status:'',delivery_status:'',error_code:'',sort:''},import:{q:'',filter:''}};
  function filterDefinitions(scope){
    if(scope==='task')return [['q','搜索','task-search'],['status','状态','task-filter'],['guide_version_id','指引','task-guide-filter'],['sort','排序','task-sort']];
    if(scope==='doc')return [['q','搜索','doc-search'],['upload_status','上传','doc-upload-filter'],['eligibility','资格','doc-qualification-filter'],['delivery_status','交付','doc-completeness-filter'],['job_status','处理','doc-status-filter'],['error_code','原因','doc-reason-filter'],['sort','排序','doc-sort']];
    if(scope==='import')return [['q','搜索','import-search'],['filter','状态','import-filter']];
    return [];
  }
  function renderFilterChips(scope){
    const box=$(scope+'-filter-chips');if(!box)return;
    const defaults=FILTER_DEFAULTS[scope]||{},chips=[];
    for(const [key,label,id] of filterDefinitions(scope)){
      const el=$(id);if(!el)continue;const value=el.value;
      if(value===defaults[key]||value==='')continue;
      const text=key==='q'?`搜索：${value}`:key==='error_code'?`原因：${reason(value)}`:`${label}：${el.options[el.selectedIndex]?.textContent||value}`;
      chips.push(`<span class="filter-chip"><span title="${esc(text)}">${esc(text)}</span><button type="button" data-clear-filter="${scope}:${key}" aria-label="移除筛选 ${esc(text)}">×</button></span>`);
    }
    if(!chips.length){box.hidden=true;box.innerHTML='';return;}
    box.hidden=false;box.innerHTML=chips.join('')+`<button type="button" class="clear-filters" data-clear-filters="${scope}">清除全部</button>`;
  }
  function clearFilter(scope,key){
    const definition=filterDefinitions(scope).find(([name])=>name===key);if(!definition)return;
    const el=$(definition[2]);if(!el)return;
    el.value=(FILTER_DEFAULTS[scope]||{})[key]??'';
    renderFilterChips(scope);changed(scope);
  }
  function clearAllFilters(scope){
    for(const [key,,id] of filterDefinitions(scope)){const el=$(id);if(el)el.value=(FILTER_DEFAULTS[scope]||{})[key]??'';}
    renderFilterChips(scope);changed(scope);
  }
  const VIEW_TITLES={overview:'任务总览',import:'新建任务',task:'任务详情',guide:'指引配置',settings:'开发设置',users:'用户管理',compare:'合同对比'};
  function renderTopbarTitle(view) {const el=$('topbar-title');el.textContent=view==='import'&&state.recover?'新建任务 · 补传':(VIEW_TITLES[view]||'');}
  function renderFooter(){const el=$('app-version');if(el)el.textContent=state.cap?.app_version?`v${state.cap.app_version}`:'—';}
  function renderBreadcrumb(view=state.view){
    const el=$('breadcrumb');if(!el)return;
    const items=[{label:'工作台',nav:'overview'}];
    const add=(label,nav=null,current=false)=>items.push({label,nav,current});
    if(view==='overview')add('任务总览',null,true);
    else if(view==='import')add('新建任务',null,true);
    else if(view==='task'){add('任务详情',state.selected?'task':null,!state.selected);if(state.selected)add(state.task?.name||'任务详情',null,true);}
    else if(view==='guide')add('指引配置',null,true);
    else if(view==='compare')add('合同对比',null,true);
    else if(view==='settings')add('开发设置',null,true);
    else if(view==='users')add('用户管理',null,true);
    else add('任务总览',null,true);
    el.innerHTML=items.map((item,index)=>`${index?'<span class="crumb-sep" aria-hidden="true">›</span>':''}${item.current?`<span aria-current="page" title="${esc(item.label)}">${esc(item.label)}</span>`:`<button type="button" class="crumb-link" data-crumb="${esc(item.nav||'overview')}">${esc(item.label)}</button>`}`).join('');
  }
  function openHelp(){const view=$('help-overlay');if(!view)return;state.focusReturn=document.activeElement;view.hidden=false;document.querySelector('.app').inert=true;$('help-close').focus();}
  function closeHelp(){const view=$('help-overlay');if(!view||view.hidden)return;view.hidden=true;if($('login-view').hidden&&$('password-view').hidden&&$('detail-overlay').hidden)document.querySelector('.app').inert=false;if(state.focusReturn){state.focusReturn.focus();state.focusReturn=null;}}
  function go(view) {if(view==='users'&&!(state.auth.mode==='password'&&state.auth.user?.role==='admin'))view='overview';if(view==='settings'&&state.auth.mode==='password')view='overview';if(!['overview','import','task','guide','settings','users','compare'].includes(view))view='overview';state.view=view;document.dispatchEvent(new CustomEvent('fundlex:view',{detail:view}));renderTopbarTitle(view);renderBreadcrumb(view);if(view==='users'&&state.auth.mode==='password'&&state.auth.user&&state.auth.user.role==='admin')loadUsers();if(view==='guide')loadGuides();document.querySelectorAll('.section').forEach(n=>n.classList.toggle('active',n.id===`view-${view}`));document.querySelectorAll('[data-nav].nav-btn').forEach(n=>{n.classList.toggle('active',n.dataset.nav===view);if(n.dataset.nav===view)n.setAttribute('aria-current','page');else n.removeAttribute('aria-current');});if(location.hash!==`#${view}`)location.hash=view;document.querySelector('.main').scrollTop=0;if(view==='task')loadDocuments();if(view==='overview'&&state.cap){loadTasks();loadOverviewStats(true);if(!state.taskGuides)loadTaskGuides(true);}}
  function formatSeconds(value){if(value==null||!Number.isFinite(Number(value)))return '—';const seconds=Math.max(0,Math.round(Number(value)));if(seconds<60)return `${seconds} 秒`;const minutes=Math.floor(seconds/60),rest=seconds%60;return rest?`${minutes} 分 ${rest} 秒`:`${minutes} 分`;}
  function formatChange(value){if(value==null||!Number.isFinite(Number(value)))return '—';const pct=Math.round(Number(value)*1000)/10;return `${pct>0?'+':''}${pct}%`;}
  function renderOverview(stats=state.overviewStats){
    const has=!!stats&&Number.isFinite(Number(stats.processed_contracts));
    const processed=has?Number(stats.processed_contracts):null;
    const completed=has?Number(stats.completed_contracts||0):null;
    const pending=has?Number(stats.pending_contracts||0):null;
    const average=has?stats.average_seconds:null;
    const exceptions=has?Number(stats.exception_contracts||0):null;
    const rate=has&&processed?Math.round(Number(stats.completion_rate||0)*1000)/10:null;
    const rateText=rate==null?'—':`${Number.isInteger(rate)?rate:rate.toFixed(1)}%`;
    $('overview-processed').textContent=has?processed:'—';
    $('overview-average').textContent=has&&average!=null?String(Math.max(0,Math.round(Number(average)))):'—';
    $('overview-completion-rate').textContent=rateText;
    $('overview-progress-label').textContent=has?`${completed} / ${processed} 份已完成 · 待处理 ${pending} 份`:'— / — 份已完成 · 待处理 — 份';
    const fill=$('overview-progress-fill');if(fill)fill.style.width=`${rate||0}%`;
    const bar=$('overview-progress');if(bar)bar.setAttribute('aria-valuenow',String(rate||0));
    $('stat-month-contracts').textContent=has?processed:'—';
    $('stat-month-contracts-note').textContent=has?`环比 ${formatChange(stats.month_over_month)}`:'环比 —';
    $('stat-completion-rate').textContent=rateText;
    $('stat-completion-note').textContent=has?`${completed} / ${processed} 份`:'— / — 份';
    $('stat-pending').textContent=has?pending:'—';
    $('stat-pending-note').textContent=has?`${Number(stats.active_tasks||0)} 个任务进行中`:'— 个任务进行中';
    $('stat-average').textContent=has?formatSeconds(average):'—';
    $('stat-exceptions').textContent=has?exceptions:'—';
    const guideHidden=state.tasksLoaded&&!state.tasksFailed&&!state.guideDismissed&&!(state.tasks||[]).length&&!$('task-search').value.trim()&&!$('task-filter').value&&!$('task-guide-filter').value;
    guideHidden?$('first-run-guide').removeAttribute('hidden'):$('first-run-guide').setAttribute('hidden','');
  }
  async function loadOverviewStats(quiet=false){const t=ticket('overview-stats');try{const stats=await json('/api/tasks/stats');if(!current(t))return;state.overviewStats=stats;renderOverview(stats);}catch(e){if(!current(t))return;state.overviewStats=null;renderOverview(null);if(!quiet&&e.code!=='CONNECTION')errorNotice(e);}}
  function guideNameForTask(task){if(!task)return '—';if(task.legacy)return '遗留任务 · 未绑定指引';const id=task.guide_snapshot?.version_id;if(!id)return '未绑定指引';const item=(state.taskGuides||[]).find(guide=>guide.id===id);return item?item.filename:`指引版本 ${id}`;}
  function renderTaskGuideFilter(){const select=$('task-guide-filter');if(!select)return;const current=select.value,items=state.taskGuides||[];select.innerHTML='<option value="">全部指引</option>'+items.map(guide=>`<option value="${esc(guide.id)}">${esc(guide.filename)}${guide.built_in?'（内置）':''}</option>`).join('');if(current&&items.some(guide=>guide.id===current))select.value=current;}
  function renderTaskRows(){const items=state.tasks||[];$('task-rows').innerHTML=items.map(taskRow).join('')||emptyRow(6,'当前条件下没有任务');}
  async function loadTaskGuides(quiet=false){if(state.auth.mode==='password'&&!state.auth.token)return;const t=ticket('task-guides');try{const payload=await json('/api/guides');if(!current(t))return;state.taskGuides=Array.isArray(payload.items)?payload.items:[];renderTaskGuideFilter();renderTaskRows();}catch(e){if(!current(t))return;if(!quiet&&e.code!=='404'&&e.code!=='CONNECTION')errorNotice(e);}}
  function evaluationCount(t){const dc=t?.delivery_counts||{};return (dc.evaluation_modified||0)+(dc.evaluation_modified_with_exceptions||0)+(dc.evaluation_unmodified||0);}
  function progressHTML(t) {const total=t?.total || 1;return [['p-done',t?taskMetrics(t).success:0],['p-fail',t?taskMetrics(t).anomaly:0],['p-excluded',t?.qualification_counts?.excluded_by_fund_type||0],['p-evaluation',evaluationCount(t)],['p-work',t?.processing || 0],['p-queue',t?.queued || 0]].map(([c,n])=>`<span class="${c}" style="width:${Math.min(100,100*n/total)}%"></span>`).join('');}
  function renderTask() {
    const t=state.task,pct=t?.total?Math.round(100*(t.completed)/t.total):0;
    $('task-status').innerHTML=t?badge(t.status):'';$('selected-task-title').textContent=t?.name || '尚未选择任务';
    $('selected-task-subtitle').textContent=t?`任务全部 ${t.total} 份 · 已上传 ${t.uploaded} 份 · 待上传 ${t.pending_upload} 份 · 接收失败 ${t.rejected} 份`:'从任务总览选择任务查看结果。';
    const qc=t?.qualification_counts||{},dc=t?.delivery_counts||{};
    $('progress-evaluation-legend').hidden=!evaluationCount(t);
    const anomaly=t?taskMetrics(t).anomaly:0;
    const processCounts=t?[['合同总数',t.total,'任务全部合同'],['已处理',t.completed,`已进入终态 · 交付完成 ${taskMetrics(t).success}`],['处理中',t.processing,'正在处理'],['排队',t.queued,'排队或等待重试'],['异常',anomaly,`失败 ${t.failed} · 接收失败 ${t.rejected} · 交付不完整 ${dc.incomplete||0}`],['整体进度',`${pct}%`,`${t.completed} / ${t.total} 份进入终态`]]:[];
    $('overall-counts').innerHTML=processCounts.map(([l,n,note])=>`<div class="mini-kpi" title="${esc(note)}"><label>${l}</label><b>${n}</b></div>`).join('');
    const business=t?[['合同总数',t.total,'任务全部合同'],['资格符合',qc.eligible||0,'通过通用资格判定'],['已排除',qc.excluded_by_fund_type||0,'特殊类型整份排除，不生成修改产物'],['资格失败',qc.failed||0,'证据不足或冲突，失败关闭'],['未判定',qc.pending||0,'尚未完成资格判定'],['产物完整',(dc.complete||0)+(dc.complete_with_exceptions||0),'已通过交付校验（含例外条款的合同需结合报告核对）'],['结果不完整',dc.incomplete||0,'存在应处理失败，不能直接使用'],['未生成',dc.not_generated||0,'未产出可交付合同文件']]:[];
    $('result-counts').innerHTML=business.map(([l,n,note])=>`<div class="batch-count" title="${esc(note)}"><b>${n}</b><span>${l}</span></div>`).join('');
    for(const id of ['task-ruleset']){const chip=$(id);const snap=t?.guide_snapshot,bound=snap?.version_id;if(bound){chip.hidden=false;chip.textContent=t.legacy?'遗留任务':'合同修订 · 指引绑定';chip.title=`任务绑定的指引版本：${bound}${snap.rules_sha256?` · SHA-256：${snap.rules_sha256}`:''}`;}else if(t?.ruleset_version){chip.hidden=false;chip.textContent=`遗留任务 · 规则 ${t.ruleset_version}`;chip.title=t.ruleset_sha256?`任务绑定的规则包 SHA-256：${t.ruleset_sha256}`:'';}else{chip.hidden=true;chip.textContent='';chip.title='';}}
    for(const action of ['export-results']){const b=document.querySelector(`[data-action="${action}"]`);if(b)b.disabled=!t;}
    const dlAll=document.querySelector('[data-action="download-all"]');if(dlAll){const ready=!!t&&((t.completed||0)+(t.rejected||0)>0);dlAll.disabled=!ready;dlAll.title=ready?`打包下载 ${t.name} 的全部合同结果`:'该任务尚无可下载的合同结果';}
    $('task-upload-label').textContent=t?`${t.uploaded} / ${t.total} 份已上传${t.rejected?` · ${t.rejected} 份接收失败`:''}${t.pending_upload?` · ${t.pending_upload} 份待补传`:''}`:'尚未选择任务';$('task-process-label').textContent=t?(t.status==='completed'?'全部处理结束':t.status==='paused'?`任务已暂停${t.pause_reason?' · '+reason(t.pause_reason):''}`:`已完成 ${t.completed} / ${t.total} 份`):'尚未选择任务';$('task-percent').textContent=t?`${pct}% · 任务总进度`:'—';$('task-overall-label').textContent=t?`${t.completed} / ${t.total} 份进入终态 · ${t.failed} 份失败关闭${t.rejected?` · ${t.rejected} 份接收失败`:''}`:'';{const id='overall-progress';$(id).innerHTML=progressHTML(t);$(id).setAttribute('role','progressbar');$(id).setAttribute('aria-label','合同处理总进度');$(id).setAttribute('aria-valuemin','0');$(id).setAttribute('aria-valuemax','100');$(id).setAttribute('aria-valuenow',String(pct));}
    $('pause-btn').textContent=t?.status==='paused'?'继续任务':'暂停任务';$('pause-btn').disabled=!t||t.legacy||t.status==='completed';$('recover-btn').disabled=!t||t.legacy||!(t.pending_upload+t.rejected)||state.uploading;
    {const select=$('task-select'),items=state.tasks.slice();if(t&&!items.some(x=>x.id===t.id))items.unshift(t);select.innerHTML='<option value="">选择任务</option>'+items.map(x=>`<option value="${esc(x.id)}" ${x.id===state.selected?'selected':''}>${esc(x.name)}</option>`).join('');}
  }
  async function loadCapabilities() {const t=ticket('cap');try{const cap=await json('/api/capabilities');if(!current(t))return;state.auth.mode=cap.auth_mode||'dev';state.auth.loginRequired=!!cap.login_required;state.auth.registrationOpen=!!cap.registration_open;if(state.auth.mode==='password'){if(!state.auth.token){state.cap=null;showLogin();return;}if(!cap.upload_limits){handleSessionExpired();return;}if(!state.auth.user){try{await loadMe();}catch(e){if(!current(t))return;if(e.code==='CONNECTION')errorNotice(e);return;}if(!current(t))return;}hideLogin();}else{hideLogin();}renderAuthUI();state.cap=cap;renderFooter();if(!state.importMode)state.importMode='revision';$('upload-limit').textContent=`仅接收 DOCX · 单文件 ≤ ${size(cap.upload_limits.max_file_bytes)}`;$('auth-note').textContent=state.auth.mode==='dev'?'开发身份通过请求头进行隔离。生产身份服务尚未配置时将关闭访问。':'当前环境使用账号登录，请求通过 Bearer 令牌进行身份隔离。';const engine=cap.engine||{},guide=engine.guide||null;const delivery=engine.delivery_mode==='formal'?'正式交付':'不可用';const guideLine=guide?`<dt>生效指引</dt><dd>${esc(guide.filename||'—')} · ${guide.built_in?'内置':'自定义'} · ${engine.actions_total} 组</dd>`:'';$('capability-details').innerHTML=`<dt>修订引擎</dt><dd>${esc(engine.id||'—')} · ${esc(delivery)}</dd>${guideLine}<dt>单文件限制</dt><dd>${size(cap.upload_limits.max_file_bytes)}</dd>`;updateDeliveryNote();renderImport();}catch(e){if(current(t)){state.cap=null;errorNotice(e);}}}
  function deliveryCounts() {const dc=state.task?.delivery_counts;if(dc)return dc;const docs=state.taskDocs||[];if(!docs.length)return null;const counts={complete:0,complete_with_exceptions:0,incomplete:0,not_generated:0,evaluation_modified:0,evaluation_modified_with_exceptions:0,evaluation_unmodified:0};for(const d of docs)if(d.delivery_status in counts)counts[d.delivery_status]+=1;return counts;}
  function updateDeliveryNote() {const note=$('doc-scope-note');if(!note||note.hidden)return;const counts=deliveryCounts();if(!counts)return;note.textContent=deliveryNoteText(counts);}
  function deliveryNoteText(counts) {const revision=(counts.evaluation_modified||0)+(counts.evaluation_modified_with_exceptions||0)+(counts.evaluation_unmodified||0);const base=`正式交付完整 ${counts.complete||0} · 含例外 ${counts.complete_with_exceptions||0} · 结果不完整 ${counts.incomplete||0} · 未生成 ${counts.not_generated||0}`;return revision?`${base} · 评测已修改 ${counts.evaluation_modified||0} · 无需修改 ${counts.evaluation_unmodified||0}`:base;}
  function taskMetrics(t){const failed=t.failed||0,rejected=t.rejected||0,dc=t.delivery_counts||{},incomplete=dc.incomplete||0;return {success:t.successful??((dc.complete||0)+(dc.complete_with_exceptions||0)),anomaly:t.exceptions??(failed+rejected+incomplete),breakdown:`失败 ${failed} · 接收失败 ${rejected} · 交付不完整 ${incomplete}（异常合同按份去重）`};}
  function taskRow(t){const m=taskMetrics(t),pct=t.total?Math.round(100*(t.completed||0)/t.total):0;const guide=guideNameForTask(t);return `<tr><td><span class="filename" title="${esc(t.name)}">${esc(t.name)}</span><span class="row-sub">${esc(new Date(t.created_at).toLocaleString('zh-CN'))}</span><span class="row-sub task-guide-name" title="${esc(guide)}">${esc(guide)}</span></td><td><strong>${t.total}</strong><span class="row-sub">份合同</span></td><td title="${esc(m.breakdown)}"><span class="task-success">${m.success}</span> / <span class="task-error">${m.anomaly}</span><span class="row-sub">成功 / 异常</span></td><td>${badge(t.status)}</td><td><div class="task-progress"><div class="progress-line mini">${progressHTML(t)}</div><small>${pct}% · ${t.completed}/${t.total} 份终态</small></div></td><td><button class="btn-link" data-task="${esc(t.id)}">查看</button></td></tr>`;}
  async function loadTasks() {const t=ticket('tasks');renderFilterChips('task');$('task-rows').setAttribute('aria-busy','true');try{const p=await json(`/api/tasks?${param({q:$('task-search').value.trim(),status:$('task-filter').value,guide_version_id:$('task-guide-filter').value,sort:$('task-sort').value,page:state.taskPage,page_size:state.taskSize})}`);if(!current(t))return;state.tasks=p.items;state.taskPage=p.page;state.tasksLoaded=true;state.tasksFailed=false;renderTaskGuideFilter();renderTaskRows();renderFilterChips('task');$('task-pagination').innerHTML=pagination('task',p.total,p.page,p.page_size);renderTask();if(!state.selected&&p.items.length)await selectTask(p.items[0].id,false);}catch(e){if(current(t)){state.tasksLoaded=true;state.tasksFailed=true;$('task-rows').innerHTML=emptyRow(6,'任务暂未加载，请检查连接后刷新');errorNotice(e);renderTask();}}finally{if(current(t))$('task-rows').removeAttribute('aria-busy');}}
  async function selectTask(id,navigate=true) {if(!id)return;state.tasksFailed=false;const t=ticket('selection');state.selected=id;state.task=null;state.docPage=1;state.taskDocs=[];state.review=null;state.reviewDecisions=new Map();state.reviewDocs=null;state.reviewDocsTask=null;state.reviewDocsKey='';$('doc-scope').textContent='';$('doc-pagination').replaceChildren();$('doc-reason-filter').innerHTML='<option value="">全部原因</option>';$('doc-empty').hidden=true;closeDetail();state.tokens.doc=(state.tokens.doc || 0)+1;$('doc-rows').innerHTML=emptyRow(7,'正在加载任务');renderTask();try{const task=await json(pathTask(id));if(!current(t)||state.selected!==id)return;state.task=task;renderBreadcrumb();renderTask();if(navigate)go('task');else if(state.view==='task')loadDocuments();}catch(e){if(current(t))errorNotice(e);}}
  function docReason(d) {if(d.upload_status==='rejected')return reason(d.error_code)||'接收校验未通过，请检查源文件后补传';if(d.upload_status==='pending')return '尚未上传，请选择本地文件补传';if(d.eligibility==='excluded_by_fund_type')return '基金类型不在本流程范围，已整份排除';if(d.error_code)return reason(d.error_code);if(d.reason_codes?.length)return reason(d.reason_codes[0]);if(['running','leased'].includes(d.job_status))return '正在处理，尚无结论';if(d.job_status==='queued')return '排队等待处理';if(d.job_status==='retry_wait')return '暂时异常，等待自动重试';if(d.delivery_status==='evaluation_modified')return '合同修订（评测）已完成，可下载评测修改版核对';if(d.delivery_status==='evaluation_modified_with_exceptions')return '合同修订（评测）已完成；有条款未自动修改，按例外清单人工核对后使用';if(d.delivery_status==='evaluation_unmodified')return '原合同已符合当前规则，无需修改';if(d.delivery_status==='complete_with_exceptions')return '合同已修订并校验通过；有条款未自动修改，请按例外清单人工核对';if(d.delivery_status==='incomplete')return '部分条款未自动修改，不能直接使用；请在「仍需人工核对」中按章节和原文检查（修订版不会标出未修改位置）';if(d.delivery_status==='complete')return '合同产物已通过交付校验，可查看报告并下载';if(d.job_status==='succeeded')return '处理已结束，未生成可交付合同文件';return '尚未生成合同产物';}
  function targetChip(doc) {const counts=doc&&doc.target_counts;if(!counts||!Number.isFinite(counts.total))return '';const phase=doc.phase?`引擎阶段：${doc.phase}`:'召回优先修订';return `<span class="chip-target" title="${esc(`${phase} · 目标条款完成情况`)}">目标 ${counts.total} · 已完成 ${counts.completed || 0} · 未完成 ${counts.unresolved || 0}</span>`;}
  function docRowClass(d){const clean=d.job_status==='succeeded'&&d.delivery_status==='complete'&&d.eligibility==='eligible';if(d.job_status==='failed'||d.upload_status==='rejected'||d.eligibility==='failed'||d.delivery_status==='incomplete'||(d.job_status==='succeeded'&&d.delivery_status==='not_generated'&&d.eligibility!=='excluded_by_fund_type'))return 'row-exception';return clean?'row-muted':'';}
  async function loadDocuments() {const name='doc',cols=7,id=state.selected,t=ticket('doc');renderFilterChips('doc');if(!id){$('doc-rows').innerHTML=emptyRow(cols,'从任务总览选择任务');return;}const values={q:$('doc-search').value.trim(),upload_status:$('doc-upload-filter').value,eligibility:$('doc-qualification-filter').value,job_status:$('doc-status-filter').value,delivery_status:$('doc-completeness-filter').value,error_code:$('doc-reason-filter').value,sort:$('doc-sort').value,page:state.docPage,page_size:state.docSize};$('doc-rows').setAttribute('aria-busy','true');try{const p=await json(`${pathTask(id)}/documents?${param(values)}`);if(!current(t)||state.selected!==id)return;state.taskDocs=p.items;state.docPage=p.page;$('doc-scope').textContent=`任务全部 ${state.task?.total ?? '—'} 份 · 匹配 ${p.total} 份`;const note=$('doc-scope-note');note.hidden=false;note.textContent=(state.cap?'本次交付：':'本次结果：')+deliveryNoteText(state.task?.delivery_counts||{});
      $('doc-rows').innerHTML=p.items.map((d,i)=>`<tr class="${docRowClass(d)}"><td><span class="filename" title="${esc(d.name)}">${esc(d.name)}</span><span class="row-sub">${size(d.size)}</span>${targetChip(d)}</td><td>${badge(d.upload_status,d.upload_status==='pending'?'待上传':null)}</td><td>${badge(d.eligibility || 'pending')}</td><td>${badge(d.delivery_status)}</td><td>${badge(d.job_status)}</td><td class="reason-cell">${esc(docReason(d))}</td><td><button class="btn-link" data-detail="${name}:${i}">${d.report_url?'查看证据':'查看状态'}</button></td></tr>`).join('')||emptyRow(cols,'当前筛选下没有匹配的合同，可调整搜索或筛选条件');$('doc-pagination').innerHTML=pagination(name,p.total,p.page,p.page_size);const selected=$('doc-reason-filter').value;const options=p.reason_options || [];$('doc-reason-filter').innerHTML='<option value="">全部原因</option>'+options.map(o=>`<option value="${esc(o.code)}">${esc(reason(o.code))}（${o.count}）</option>`).join('');if(selected&&!options.some(o=>o.code===selected))$('doc-reason-filter').insertAdjacentHTML('beforeend',`<option value="${esc(selected)}">${esc(reason(selected))}</option>`);$('doc-reason-filter').value=selected;
    }catch(e){if(current(t)&&state.selected===id){$('doc-rows').innerHTML=emptyRow(cols,'合同列表暂未加载，请刷新');errorNotice(e);}}finally{if(current(t))$('doc-rows').removeAttribute('aria-busy');}}
  async function refresh(quiet=false) {const id=state.selected,selectionToken=state.tokens.selection,t=ticket('refresh');await loadCapabilities();if(!current(t))return;if(state.auth.mode==='password'&&!state.auth.token)return;await loadTasks();if(!current(t))return;if(id&&state.selected===id&&selectionToken===state.tokens.selection)try{const previous=state.task?.status;const task=await json(pathTask(id));if(!current(t)||state.selected!==id||selectionToken!==state.tokens.selection)return;state.task=task;renderTask();if(previous&&previous!==task.status&&task.status==='completed'&&['uploading','queued','running','paused'].includes(previous)){notify(`${task.name}：处理结束，可查看结果`,false,task.id);if(document.visibilityState==='hidden')document.title=`✓ ${task.name} 处理结束 · FundLex`;}}catch(e){if(current(t))errorNotice(e);}if(current(t)&&state.view==='task')await loadDocuments();if(current(t)&&state.view==='overview')await loadOverviewStats(quiet);if(current(t)&&state.view==='overview'&&(!quiet||!state.taskGuides))await loadTaskGuides(quiet);if(current(t)&&state.view==='guide'&&!state.guideBusy)await loadGuides(true);}
  function importAnalysis() {const seen=new Set();const checked=state.imports.map(f=>{let issue='';const key=f.name.toLowerCase()+'|'+f.size;if(!/\.docx$/i.test(f.name))issue='不支持格式：仅接收 DOCX';else if(!f.size)issue='空文件，无法接收';else if(state.cap&&f.size>state.cap.upload_limits.max_file_bytes)issue=`超过单文件 ${size(state.cap.upload_limits.max_file_bytes)} 限制`;else if(seen.has(key))issue='疑似重复：文件名与大小相同';else if(state.recover&&!f.client_id)issue='与待补传清单不匹配';else seen.add(key);return {...f,issue:issue||f.serverIssue||''};});return {checked,accepted:checked.filter(f=>!f.issue),issues:checked.filter(f=>!!f.issue).length,total:checked.reduce((s,f)=>s+f.size,0)};}
  function nameError(show) {const value=$('task-name').value.trim(),bad=show&&!value,field=$('task-name-error');field.hidden=!bad;$('task-name').setAttribute('aria-invalid',bad?'true':'false');$('task-name').classList.toggle('invalid',bad);return !bad;}
  function syncImportMode() {const select=$('import-mode'),note=$('import-mode-note');if(!select)return;select.value='revision';select.disabled=true;if(!note)return;if(state.recover){note.textContent='补传沿用原任务的处理模式，不能切换。';return;}note.textContent=guideReady()?'使用当前指引修订合同，产出修订痕迹与最终版；可逐条审查接受或拒绝。':'当前指引不可用，暂时不能创建任务；请先在「指引配置」启用可用指引。';}
  function renderImport() {$('export-pending').hidden=!state.recover;$('cancel-recover').hidden=!state.recover;syncImportMode();renderGuideBinding();renderFilterChips('import');renderUploadProgress();const a=importAnalysis(),q=$('import-search').value.trim().toLowerCase(),filter=$('import-filter').value,matching=a.checked.filter(f=>f.name.toLowerCase().includes(q)&&(!filter||(filter==='accepted'?!f.issue:!!f.issue))),pages=Math.max(1,Math.ceil(matching.length/state.importSize));state.importPage=Math.min(state.importPage,pages);const shown=matching.slice((state.importPage-1)*state.importSize,state.importPage*state.importSize);$('import-stats').innerHTML=[['文件总数',state.imports.length],['总大小',size(a.total)],['可接收',a.accepted.length],['异常',a.issues]].map(([l,n])=>`<span class="inline-kpi"><b>${n}</b>${l}</span>`).join('');$('import-validation').textContent=state.recover?`补传模式：待补传 ${state.recover.manifest.length} 份 · 已匹配 ${state.imports.filter(f=>f.client_id).length} 份。`:'异常文件不会提交，请检查重复文件。';$('import-rows').innerHTML=shown.map(f=>{const cls=f.issue?'row-exception':f.received?'row-muted':'';const statusLabel=f.issue||(f.received?'已接收':state.uploading?'上传中':'可接收');return `<tr class="${cls}"><td><span class="filename" title="${esc(f.name)}">${esc(f.name)}</span></td><td>${size(f.size)}</td><td>${badge(f.issue?'rejected':f.received?'accepted':state.uploading?'running':'accepted',statusLabel)}</td><td><div class="row-actions"><button class="btn-link" data-replace="${esc(f.id)}" ${state.uploading?'disabled':''} aria-label="替换 ${esc(f.name)}">替换</button><button class="btn-link" data-remove="${esc(f.id)}" ${state.uploading?'disabled':''} aria-label="移除 ${esc(f.name)}">移除</button></div></td></tr>`;}).join('');$('import-empty').hidden=matching.length>0;$('import-empty').innerHTML='<strong>当前清单没有匹配文件</strong>选择多个 DOCX、文件夹，或调整筛选。';$('import-pagination').innerHTML=pagination('import',matching.length,state.importPage,state.importSize);$('task-check').innerHTML=[['任务文件',`${state.recover?.total ?? state.imports.length} 份`],['本次可接收',`${a.accepted.length} 份`],['待确认异常',`${a.issues} 份`],['可接收总大小',size(a.accepted.reduce((n,f)=>n+f.size,0))]].map(([l,n])=>`<div class="plan-row"><strong>${l}</strong><span>${n}</span></div>`).join('');$('submit-task').disabled=!a.accepted.length||state.uploading||!state.cap||(!state.recover&&!guideReady());$('submit-task').textContent=state.uploading?'正在上传…':state.recover?'补传到原任务':'创建任务并上传';$('task-name').disabled=!!state.recover;document.querySelectorAll('[data-action="choose-files"],[data-action="choose-folder"],[data-action="clear-import"]').forEach(n=>n.disabled=state.uploading);}
  function renderUploadProgress(){const box=$('upload-progress');if(!box)return;const p=state.uploadProgress;if(!p||!p.visible){box.hidden=true;return;}const pct=Math.max(0,Math.min(100,Number(p.pct)||0));box.hidden=false;$('upload-progress-label').textContent=p.label||'正在上传';$('upload-progress-pct').textContent=`${pct}%`;$('upload-progress-line').innerHTML=`<span class="${p.error?'p-fail':'p-done'}" style="width:${pct}%"></span>`;$('upload-progress-meta').textContent=p.meta||'';}
  function resetImportStages(task=null) {$('upload-message').textContent=task?'重新选择未接收的本地文件；按原名与大小匹配，已接收文件无需再次选择。':'选择或拖入 DOCX 合同，确认文件清单后创建任务。';}
  function newTask() {state.importSession++;state.tokens.recovery=(state.tokens.recovery||0)+1;state.recover=null;state.imports=[];state.createKey=null;state.importPage=1;state.uploadProgress=null;state.replaceTarget=null;$('task-name').value='';resetImportStages();renderImport();go('import');$('task-name').focus();}
  function replaceFile(id,file){const index=state.imports.findIndex(f=>f.id===id);if(index<0||!file)return;const old=state.imports[index];const client_id=state.recover&&old.name===file.name&&old.size===file.size?old.client_id:null;state.imports[index]={id:old.id,file,name:file.name,size:file.size,client_id,received:false};state.createKey=null;renderImport();toast(`已替换为：${file.name}`);}
  function addFiles(files) {if(state.uploading)return;if(state.recover&&!state.task)return;for(const file of files){let client_id=null;if(state.recover){const used=new Set(state.imports.map(f=>f.client_id));client_id=state.recover.manifest.find(d=>d.name===file.name&&d.size===file.size&&!used.has(d.client_id))?.client_id || null;}state.imports.push({id:crypto.randomUUID(),file,name:file.name,size:file.size,client_id});}state.createKey=null;state.importPage=1;renderImport();}
  async function recover() {if(!state.task||state.task.legacy||state.uploading)return;const id=state.selected,t=ticket('recovery');try{const manifest=[];let page=1,total=Infinity;while(manifest.length<total){const p=await json(`${pathTask(id)}/documents?page=${page++}&page_size=100`);if(!current(t)||state.selected!==id)return;manifest.push(...p.items);total=p.total;if(!p.items.length)break;}const task=await json(pathTask(id));if(!current(t)||state.selected!==id)return;state.importSession++;state.recover={...task,manifest:manifest.filter(d=>d.upload_status!=='accepted')};state.imports=[];state.importPage=1;$('task-name').value=task.name;resetImportStages(task);renderImport();go('import');flash('任务清单已恢复：可先导出待补传清单；浏览器重载不能保留本地文件权限，需重新选择文件补传。');}catch(e){if(current(t))errorNotice(e);}}
  function submissionPayload(name,files) {const payload={name,files:files.map(f=>({client_id:f.client_id,name:f.name,size:f.size}))};const engine=state.cap?.engine;if(engine?.id)payload.engine_id=engine.id;return payload;}
  async function submit() {
    if(state.uploading||!state.cap)return;
    if(!state.recover&&!guideReady()){notice('当前指引不可用，请先启用可用指引。',true);return;}
    const analysis=importAnalysis(),name=$('task-name').value.trim();
    if(!analysis.accepted.length)return;
    if(!nameError(true)){$('task-name').focus();return;}
    const epoch=state.epoch,session=state.importSession,selection=state.tokens.selection;
    const uploadToken=crypto.randomUUID(),sessionFiles=analysis.accepted.map(f=>({...f}));
    const limits={...state.cap.upload_limits};
    let recovery=state.recover,taskId=recovery?.id,task=null,started=false;
    state.uploadToken=uploadToken;state.uploading=true;
    const active=()=>identityCurrent(epoch)&&state.uploadToken===uploadToken;
    const ownsDraft=()=>active()&&state.importSession===session;
    const progress=value=>{if(ownsDraft()){state.uploadProgress=value;renderUploadProgress();}};
    const message=text=>{if(ownsDraft())$('upload-message').textContent=text;};
    const acceptTask=value=>{task=value;if(state.selected===taskId){state.task=value;renderTask();}};
    const syncDraft=()=>{if(ownsDraft()){state.recover=recovery;renderImport();}};
    progress({visible:true,pct:0,label:'准备上传',meta:''});renderImport();
    try {
      if(!taskId){
        state.createKey ||= crypto.randomUUID();
        for(const f of sessionFiles){f.client_id ||= crypto.randomUUID();const entry=state.imports.find(x=>x.id===f.id);if(entry)entry.client_id=f.client_id;}
        task=await json('/api/tasks',{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':state.createKey},body:JSON.stringify(submissionPayload(name,sessionFiles))});
        if(!active())return;
        taskId=task.id;recovery={...task,manifest:sessionFiles.map(f=>({client_id:f.client_id,name:f.name,size:f.size}))};
        if(ownsDraft()&&state.tokens.selection===selection)await selectTask(taskId,false);
        syncDraft();
      }
      started=true;let processed=0,rejected=0;
      const groups=[];let group=[],bytes=0;
      for(const f of sessionFiles){if(group.length&&(group.length>=limits.max_request_files||bytes+f.size>limits.max_request_bytes)){groups.push(group);group=[];bytes=0;}group.push(f);bytes+=f.size;}
      if(group.length)groups.push(group);
      message('正在逐份接收合同；网络中断后可以补传，任务规模会保留。');
      for(const [index,files] of groups.entries()){
        if(!active())return;
        const label=`正在上传第 ${index+1} / ${groups.length} 组`;
        progress({visible:true,pct:0,label,meta:`${files.length} 份文件`});
        const form=new FormData();form.append('client_ids',JSON.stringify(files.map(f=>f.client_id)));files.forEach(f=>form.append('files',f.file,f.name));
        try{
          const payload=await uploadRequest(`${pathTask(taskId)}/uploads`,form,(loaded,total)=>{
            if(!active())return;
            const pct=Math.min(100,Math.round(100*loaded/total));
            progress({visible:true,pct,label,meta:`${files.length} 份文件 · 已接收 ${task?.uploaded||0} 份`});
            message(pct===100?'传输完成，正在接收校验…':`正在传输 · ${pct}%`);
          });
          if(!active())return;
          for(const receipt of payload.receipts){
            const received=receipt.status!=='rejected';if(!received)rejected++;
            if(received)recovery.manifest=recovery.manifest.filter(f=>f.client_id!==receipt.client_id);
            if(ownsDraft()){const entry=state.imports.find(f=>f.client_id===receipt.client_id);if(entry){entry.received=received;entry.serverIssue=received?'':reason(receipt.error_code)||'接收校验未通过，请检查源文件后补传';}}
          }
          processed+=files.length;recovery={...recovery,...payload.task};acceptTask(payload.task);syncDraft();
          message(`本次已尝试 ${processed} / ${sessionFiles.length} 份，${rejected} 份接收失败。`);
        }catch(e){
          if(!active()||e.name==='AbortError')return;
          errorNotice(e,'上传中断：');progress({visible:true,pct:0,error:true,label:'上传中断',meta:'已接收文件保留，可在任务详情补传。'});break;
        }
      }
      if(!active())return;
      task=await json(`${pathTask(taskId)}/seal`,{method:'POST'});if(!active())return;
      acceptTask(task);recovery={...recovery,...task};
      const pending=(task.pending_upload||0)+(task.rejected||0);
      if(ownsDraft()){
        state.imports=state.imports.filter(f=>!f.received);state.recover=recovery;
        progress({visible:true,pct:100,label:pending?'上传结束（有未接收文件）':'上传完成',meta:`已接收 ${task.uploaded} / ${task.total} 份 · 待补传 ${pending} 份`});renderImport();
      }
      flash(`${name}：${pending?'上传已结束，未接收合同可继续补传。':'文件已全部接收，可在任务详情查看处理进度。'}`);
      await loadTasks();
      if(ownsDraft()&&!pending){state.recover=null;state.imports=[];state.createKey=null;$('task-name').value='';if(state.selected===taskId&&state.view==='import')go('task');}
    }catch(e){if(active())errorNotice(e,'提交未完成：');}
    finally{if(active()){state.uploading=false;renderImport();if(started)renderTask();}}
  }
  async function togglePause() {const id=state.selected,task=state.task;if(!task)return;const t=ticket('control');$('pause-btn').disabled=true;try{const p=await json(`${pathTask(id)}/${task.status==='paused'?'resume':'pause'}`,{method:'POST'});if(!current(t)||state.selected!==id)return;state.task=p;renderTask();await loadDocuments();if(current(t)&&state.selected===id)flash(p.status==='completed'?'任务已处理结束，结果可查看。':p.status==='paused'?'整个任务已暂停，正在执行的合同可安全结束。':'任务已继续。');}catch(e){if(current(t))errorNotice(e);}finally{if(current(t)&&state.selected===id)renderTask();}}
  async function download(url,filename) {const t=ticket('download');try{const {response,epoch}=await api(url);const blob=await response.blob();if(!current(t)||!identityCurrent(epoch))return;const disposition=response.headers.get('Content-Disposition')||'';const encoded=disposition.match(/filename\*=UTF-8''([^;]+)/i),plain=disposition.match(/filename="([^"]+)"/i);if(encoded){try{filename=decodeURIComponent(encoded[1]);}catch{}}else if(plain)filename=plain[1];const object=URL.createObjectURL(blob),a=document.createElement('a');a.href=object;a.download=filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(object),1000);}catch(e){if(current(t))errorNotice(e,'下载失败：');}}
  function csvEscape(value){const s=String(value??'');return /[",\n\r]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s;}
  function downloadText(text,filename,mime='text/csv;charset=utf-8'){const blob=new Blob([text],{type:mime});const object=URL.createObjectURL(blob),a=document.createElement('a');a.href=object;a.download=filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(object),1000);}
  async function exportResults(){const id=state.selected;if(!id)return;const button=document.querySelector('[data-action="export-results"]');if(button)button.disabled=true;const t=ticket('export');try{const values={q:$('doc-search').value.trim(),upload_status:$('doc-upload-filter').value,eligibility:$('doc-qualification-filter').value,job_status:$('doc-status-filter').value,delivery_status:$('doc-completeness-filter').value,error_code:$('doc-reason-filter').value,sort:$('doc-sort').value,page_size:200,page:1};let all=[],total=Infinity,page=1;while(all.length<total&&page<=100){const p=await json(`${pathTask(id)}/documents?${param({...values,page})}`);if(!current(t)||state.selected!==id)return;all.push(...p.items);total=p.total;if(!p.items.length)break;page++;}const rows=[['序号','文件名','资格','处理状态','交付完整性','业务提示','原始原因码']].concat(all.map((d,i)=>[i+1,d.name,labels[d.eligibility||'pending']||'未判定',labels[d.job_status]||d.job_status,labels[d.delivery_status]||d.delivery_status,docReason(d),(d.reason_codes||[]).join('；')||d.error_code||'']));const csv='\ufeff'+rows.map(r=>r.map(csvEscape).join(',')).join('\r\n');downloadText(csv,`${state.task?.name||'任务'}_结果清单.csv`);toast(`已导出 ${all.length} 条结果清单（状态清单，不是合同交付）`);}catch(e){if(current(t))errorNotice(e,'导出失败：');}finally{if(button)button.disabled=false;}}
  function exportPending(){const recovering=state.recover;if(!recovering)return;const rows=[['文件名','大小(字节)','状态']].concat(recovering.manifest.map(d=>[d.name,d.size,d.upload_status==='rejected'?'接收失败':'待上传']));const csv='\ufeff'+rows.map(r=>r.map(csvEscape).join(',')).join('\r\n');downloadText(csv,`${recovering.name||state.task?.name||'任务'}_待补传清单.csv`);toast(`已导出待补传清单 ${recovering.manifest.length} 条`);}
  const proof = item => {if(typeof item==='string')return item?quoteBox('合同原文引用',item):'';if(!item||typeof item!=='object')return '';const text=item.quote || item.text || item.original_text || '';if(!text)return '';return quoteBox('合同原文引用',text);};
  const quoteBox = (label,text,cls='') => `<div class="evidence quote${cls?' '+cls:''}" title="点击展开或收起"><small class="quote-label">${esc(label)}</small><span class="quote-text">${esc(text)}</span></div>`;
  // 业务可读的条款改动：章节名 + 状态 + 改之前/改成了什么（不展示位置、字符偏移、哈希等技术字段）。
  function changedClauses(report,doc) {
    const groups=Array.isArray(report?.guide?.groups)?report.guide.groups:[];
    const groupOf=ruleId=>groups.find(g=>g&&g.rule_id===ruleId) || null;
    const sectionOf=ruleId=>{const g=groupOf(ruleId);return (g&&(g.section_hint||g.title)) || (ruleId?`条款 ${ruleId}`:'');};
    const targets=Array.isArray(report?.targets)?report.targets:[];
    const targetById=new Map(targets.map(t=>[t&&t.target_id,t]));
    const edits=Array.isArray(report?.plan?.edits)?report.plan.edits:[];
    const seen=new Set(),rows=[];
    for(const e of edits){if(!e)continue;seen.add(e.target_id);const t=targetById.get(e.target_id) || {};for(const c of e.components||[])if(c.target_id)seen.add(c.target_id);const c=(Array.isArray(e.components)&&e.components.length===1&&e.components[0]) || {};const before=e.expected_old_text || c.expected_old_text || t.quote || '';const after=e.replacement ?? '';rows.push({rule:e.rule_id,section:sectionOf(e.rule_id),state:doc&&['final','working_final','redline','working_redline'].some(kind=>doc.downloads?.[kind])?'applied':'planned',reason:t.reason || '',operation:e.operation,before,after});}
    for(const t of targets){if(!t||seen.has(t.target_id))continue;if(!['needs_edit','satisfied'].includes(t.state))continue;rows.push({rule:t.rule_id,section:sectionOf(t.rule_id),state:t.state,reason:t.reason || '',before:t.quote || '',after:''});}
    return rows;
  }
  function unresolvedIssuesHTML(report, summary) {
    const issues=Array.isArray(summary?.issues)?summary.issues:[];
    if(!issues.length)return '';
    const groups=Array.isArray(report?.guide?.groups)?report.guide.groups:[];
    const targets=Array.isArray(report?.targets)?report.targets:[];
    const groupOf=id=>groups.find(g=>g&&String(g.rule_id)===String(id))||null;
    const quoteFor=item=>{
      if(item.quote)return {text:item.quote,exact:item.quote_exact_site!==false};
      const same=targets.find(t=>t&&String(t.rule_id)===String(item.rule_id)&&String(t.location||'')===String(item.location||'')&&t.quote);
      if(same)return {text:same.quote,exact:true};
      const sibling=targets.find(t=>t&&String(t.rule_id)===String(item.rule_id)&&t.quote);
      return sibling?{text:sibling.quote,exact:false}:null;
    };
    const cards=issues.map((item,index)=>{
      const group=groupOf(item.rule_id)||{};
      const title=item.title||group.title||'未能自动修改的条款';
      const section=item.section||group.section_hint||'';
      const reason=item.business_reason||'该规则未自动修改，需要人工核对。';
      const requirement=item.requirement||group.requirement||'';
      const found=quoteFor(item);
      const note=item.review_note||(found?.exact
        ?'该规则未写入修订版，修订痕迹中不会出现本处；请在 Word 中搜索下面这段原文核对。'
        :'该规则未写入修订版，修订痕迹中不会出现本处；请先核对下面这段同类原文。');
      return `<div class="candidate manual-review-item">
        <p><strong>${index+1}. ${esc(title)}</strong>${section?` <span class="chip">${esc(section)}</span>`:''}</p>
        <p>${esc(reason)}</p>
        ${requirement?`<details class="action-evidence"><summary>查看指引要求</summary><p>${esc(requirement)}</p></details>`:''}
        ${found?quoteBox(found.exact?'合同中对应原文':'同规则参考原文（非本处）',found.text):''}
        <p class="subnote">${esc(note)}</p>
        <details class="action-evidence"><summary>技术信息（支持人员）</summary><p>内部规则编号：${esc(item.rule_id||'—')}${item.location?` · 文档位置：${esc(item.location)}`:''}${item.obligation_id?` · 义务标识：${esc(item.obligation_id)}`:''}</p></details>
      </div>`;
    }).join('');
    return `<div class="detail-section"><h3>仍需人工核对 · ${issues.length} 项</h3>
      <p class="subnote">以下规则没有自动写入修订版，因此<strong>修订痕迹里不会出现这些位置</strong>；请按“章节 + 原文”在合同或工作文件中核对。修订版仍是未完成的工作文件，不能直接当作最终合同。</p>
      ${cards}</div>`;
  }
  function clauseRow(row) {
    const op=row.operation||'';
    const status=row.state;
    const after=row.after && row.after.trim()?row.after:(op==='delete'?'':'');
    const beforeBlock=row.before?quoteBox('改之前',row.before,'quote-before'):'';
    const afterBlock=after?quoteBox(row.state==='planned'?'拟修改为（尚未生成）':'改成了什么',after,'quote-after'):(op==='delete'?quoteBox(row.state==='planned'?'拟修改为（尚未生成）':'改成了什么','（删除该句）','quote-after'):'');
    const compare=(beforeBlock||afterBlock)?`<div class="clause-compare">${beforeBlock}${afterBlock}</div>`:'<p class="subnote">报告未提供修改对照。</p>';
    const reasonText=row.reason?(reasons[row.reason]?reason(row.reason):row.reason):'';
    return `<details class="action-evidence"><summary><span class="clause-section">${esc(row.section||'条款')}</span> ${badge(status,row.state==='satisfied'?'已符合':row.state==='applied'?'已修改':null)}</summary>${reasonText?`<p>${esc(reasonText)}</p>`:''}${compare}</details>`;
  }
  function selectedContractLabel(doc){return ['complete','complete_with_exceptions'].includes(doc.delivery_status)?'最终版合同':'工作文件（未完成）';}
  function revisionSection(doc,report) {
    const delivery=report?.delivery_status || doc.delivery_status;
    const downloads=doc.downloads || {};
    const hasRedline=Boolean(downloads.working_redline || downloads.redline);
    if(!hasRedline||doc.execution_mode==='evaluation') return '';
    return `<div class="detail-section" id="revision-section"><h3>逐条审查修订</h3>
      <p class="subnote">在下方查看合同实际呈现，逐条选择接受或拒绝修订（与在 Word 中操作一致），再生成选择版合同。未完成交付的合同仍为工作文件，请结合报告核对。</p>
      <div class="detail-actions"><button class="btn btn-sm btn-primary" data-action="open-review">打开修订审查</button><button class="btn btn-sm" data-action="accept-all">一键接受全部修订</button></div>
      <p class="subnote" id="review-status"></p></div>`;
  }
  function reviewNavInfo(review){
    const docs=review.docs&&review.docs.length?review.docs:[review.doc];
    const index=Math.max(0,docs.findIndex(d=>d.document_id===review.doc.document_id));
    return {docs,index,total:docs.length,prev:index>0?docs[index-1]:null,next:index<docs.length-1?docs[index+1]:null};
  }
  function reviewDecisionsSave(){const review=state.review;if(!review||!review.doc)return;state.reviewDecisions.set(review.doc.document_id,{...review.chosen});}
  function renderReview(){
    const review=state.review, body=$('detail-body'); if(!review||!body) return;
    const chosen=review.chosen || {};
    const nav=reviewNavInfo(review);
    const items=review.revisions.map(r=>{
      const verdict=chosen[r.del_id] || 'accept';
      const before=r.before && r.before.trim() ? quoteBox('原文',r.before,'quote-before') : '';
      const after=r.after && r.after.trim() ? quoteBox('修改为',r.after,'quote-after') : quoteBox('修改为','（删除该句）','quote-after');
      const ops={insert:'新增',delete:'删除',replace:'替换'};
      return `<li class="rev-item ${verdict==='reject'?'rejected':''} ${String(review.active)===String(r.del_id)?'active':''}" data-rev-item="${r.del_id}" tabindex="-1">
        <div class="rev-head"><span class="rid">#${r.index}</span>${r.rule_id?`<span class="rule">${esc(r.rule_id)}</span>`:''}
          <span class="rev-op">${ops[r.operation]||esc(r.operation||'修改')}</span>
          <label><input type="checkbox" data-rev-toggle="${r.del_id}" ${verdict==='accept'?'checked':''} aria-label="接受第 ${r.index} 条修订"> 接受</label></div>
        ${r.section?`<p class="rev-sec">${esc(r.section)}</p>`:''}
        <div class="clause-compare">${before}${after}</div></li>`;
    }).join('');
    body.innerHTML=`<div class="review-layout">
        <div class="review-doc-wrap"><div class="review-toolbar"><strong>合同呈现</strong>
          <span class="subnote" id="review-count"></span>
          <span class="review-nav">
            <button class="btn btn-sm" data-action="review-prev" ${nav.prev?'':'disabled'} title="${nav.prev?`上一份：${esc(nav.prev.name)}`:'已经是第一份'}">← 上一份</button>
            <button class="btn btn-sm" data-action="review-next" ${nav.next?'':'disabled'} title="${nav.next?`下一份：${esc(nav.next.name)}`:'已经是最后一份'}">下一份 →</button>
            <span class="subnote" id="review-nav">第 ${nav.index+1} / ${nav.total} 份</span>
          </span>
          <span class="spacer"></span>
          <button class="btn btn-sm" data-action="review-accept-all">全部接受</button>
          <button class="btn btn-sm" data-action="review-reject-all">全部拒绝</button></div>
          <div class="review-doc" id="review-doc">${review.html}</div></div>
        <aside class="review-list"><h3>修订清单 · ${review.revisions.length} 条 <span class="review-kbd">A 接受 · R 拒绝</span></h3>
          <ol class="rev-list">${items||'<li class="subnote">本合同没有可选择的修订。</li>'}</ol></aside>
      </div>
      <div class="review-actions"><button class="btn btn-primary" data-action="generate-selected">生成选择版合同</button>
        <button class="btn" data-action="review-close">返回报告</button>
        <span class="subnote" id="review-message"></span></div>
      <p class="subnote">提示：把某条修订改为“不接受”后，交付包会同时给出「（全量痕迹版）」（引擎全部改动）
        和「（选择修订版）」（只保留你接受的修订，接受它的全部修订即得到最终版）；若全部保持默认接受，
        只给出「（全量痕迹版）」，因为它已经等于最终版。快捷键：A 接受当前选中修订，R 拒绝；切换合同前会保留当前勾选。</p>`;
    syncReview();
  }
  function revisionNodes(revision){
    const ids=revision.revision_ids?.length?revision.revision_ids:[revision.del_id,revision.ins_id??Number(revision.del_id)+1];
    return ids.flatMap(id=>[...document.querySelectorAll(`#review-doc [data-rev="${CSS.escape(String(id))}"]`)]);
  }
  function syncReview(){
    const review=state.review; if(!review) return;
    const chosen=review.chosen || {};
    let accepted=0;
    for(const r of review.revisions){
      const verdict=chosen[r.del_id] || 'accept';
      if(verdict==='accept') accepted++;
      const nodes=revisionNodes(r);
      nodes.forEach(n=>{n.classList.toggle('rejected',verdict==='reject');n.classList.toggle('active',String(review.active)===String(r.del_id));});
      const item=document.querySelector(`[data-rev-item="${r.del_id}"]`);
      if(item){const input=item.querySelector('[data-rev-toggle]');if(input)input.checked=verdict==='accept';item.classList.toggle('rejected',verdict==='reject');item.classList.toggle('active',String(review.active)===String(r.del_id));}
    }
    const count=$('review-count');
    if(count) count.textContent=`共 ${review.revisions.length} 条修订 · 已选接受 ${accepted} 条 · 已选拒绝 ${review.revisions.length-accepted} 条`;
  }
  function setRevision(delId,verdict,announce=true){
    const review=state.review;if(!review||state.selectionBusy?.doc===review.doc)return;
    review.chosen[delId]=verdict;review.active=delId;reviewDecisionsSave();syncReview();
    if(announce){const item=review.revisions.find(r=>String(r.del_id)===String(delId));toast(`第 ${item?item.index:delId} 条修订已${verdict==='accept'?'接受':'拒绝'}`);}
  }
  function setAllRevisions(verdict){
    const review=state.review;if(!review||state.selectionBusy?.doc===review.doc)return;
    for(const r of review.revisions)review.chosen[r.del_id]=verdict;
    reviewDecisionsSave();renderReview();
    toast(verdict==='accept'?`已全部标记接受（${review.revisions.length} 条）`:`已全部标记拒绝（${review.revisions.length} 条）`);
  }
  function focusRevision(delId){
    const review=state.review;if(!review)return;
    review.active=delId;
    const entry=review.revisions.find(r=>String(r.del_id)===String(delId));
    const node=entry?revisionNodes(entry)[0]:null;
    if(node)node.scrollIntoView({block:'center',behavior:'smooth'});
    syncReview();
  }
  async function reviewDocumentList(doc){
    const id=state.selected,epoch=state.epoch;if(!id)return [doc];
    const values={q:$('doc-search').value.trim(),upload_status:$('doc-upload-filter').value,eligibility:$('doc-qualification-filter').value,job_status:$('doc-status-filter').value,delivery_status:$('doc-completeness-filter').value,error_code:$('doc-reason-filter').value,sort:$('doc-sort').value};
    const key=`${id}|${JSON.stringify(values)}`;
    if(state.reviewDocs&&state.reviewDocsTask===id&&state.reviewDocsKey===key)return state.reviewDocs;
    let all=[],total=Infinity,page=1;
    try{
      while(all.length<total&&page<=100){const p=await json(`${pathTask(id)}/documents?${param({...values,page,page_size:200})}`);if(!identityCurrent(epoch)||state.selected!==id)throw stale();all.push(...p.items);total=p.total;if(!p.items.length)break;page++;}
    }catch(e){if(e.name!=='AbortError')errorNotice(e);return [doc];}
    const docs=all.filter(d=>d.downloads&&(d.downloads.redline||d.downloads.working_redline));
    if(!docs.some(d=>d.document_id===doc.document_id))docs.unshift(doc);
    state.reviewDocs=docs;state.reviewDocsTask=id;state.reviewDocsKey=key;
    return docs;
  }
  async function openReview(target=state.detail){
    const doc=target; if(!doc) return;
    const t=ticket('review');state.review=null;
    const body=$('detail-body');
    body.innerHTML='<div class="empty">正在生成合同呈现与修订清单…</div>';
    try{
      const docs=await reviewDocumentList(doc);
      if(!current(t)||state.detail!==doc || $('detail-overlay').hidden) return;
      const base=doc.review_url || `${pathDoc(doc)}/revisions`;
      const view=await json(base);
      if(!current(t)||state.detail!==doc || $('detail-overlay').hidden) return;
      const chosen=state.reviewDecisions.get(doc.document_id)||{};
      const first=view.revisions&&view.revisions[0];
      state.review={...view,doc,chosen,active:first?first.del_id:null,docs};
      renderReview();
    }catch(e){
      if(!current(t)||state.detail!==doc||$('detail-overlay').hidden)return;
      body.innerHTML='<div class="empty">无法生成合同呈现，请稍后重试。</div>';
      errorNotice(e);
    }
  }
  async function switchReview(direction){
    const review=state.review;if(!review)return;
    reviewDecisionsSave();
    const docs=review.docs&&review.docs.length?review.docs:[review.doc];
    const index=Math.max(0,docs.findIndex(d=>d.document_id===review.doc.document_id));
    const target=docs[index+direction];if(!target)return;
    state.detail=target;$('detail-title').textContent=target.name;
    await openReview(target);
  }
  function closeReview(){reviewDecisionsSave();state.review=null;state.tokens.review=(state.tokens.review||0)+1;const doc=state.detail;if(doc) showDetail(doc);}
  async function generateSelected(all){
    const doc=state.detail, review=state.review; if(!doc||state.selectionBusy) return;
    const operation={epoch:state.epoch,doc};state.selectionBusy=operation;
    const active=()=>identityCurrent(operation.epoch)&&state.selectionBusy===operation;
    const label=selectedContractLabel(doc);
    const controls=[...$('detail-body').querySelectorAll('button,input')].map(el=>({el,disabled:el.disabled}));controls.forEach(({el})=>el.disabled=true);
    const message=$('review-message');
    const decisions=all==='accept'?null:review?review.revisions.map(r=>({del_id:r.del_id,
      decision:(review.chosen||{})[r.del_id]||'accept'})):null;
    if(message) message.textContent=`正在生成${label}…`;
    try{
      const url=all==='accept'?`${pathDoc(doc)}/accept-all`:`${pathDoc(doc)}/decisions`;
      const result=await json(url,all==='accept'
        ?{method:'POST'}
        :{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({decisions})});
      if(!active())return;
      const accepted=(result.accepted||[]).length, rejected=(result.rejected||[]).length;
      if(state.detail!==doc||$('detail-overlay').hidden){toast(`${doc.name}：${label}已生成，可重新打开报告下载。`);return;}
      if(message) message.textContent=`已生成${label}：接受 ${accepted} 条，拒绝 ${rejected} 条。`;
      await refresh();
      if(!active()||state.detail!==doc||$('detail-overlay').hidden)return;
      if(!doc.downloads) doc.downloads={};
      doc.downloads.selected_final=result.download_url;
      const dl=`<button class="btn btn-primary btn-sm" data-action="download-selected">↓ 下载${label}</button>`;
      if(message) message.innerHTML=esc(message.textContent)+` ${dl}`;
      const status=$('review-status');
      if(status) status.textContent=rejected>0
        ?`已生成${label}：接受 ${accepted} 条，拒绝 ${rejected} 条。结果包里会同时给出「（全量痕迹版）」和只含接受修订的「（选择修订版）」。`
        :`已生成${label}：接受 ${accepted} 条，未拒绝任何修订。结果与引擎一致，只给出「（全量痕迹版）」。`;
    }catch(e){
      if(!active())return;
      if(message&&state.detail===doc) message.textContent='生成失败，请稍后重试。';
      errorNotice(e);
    }finally{if(active()){state.selectionBusy=null;controls.filter(({el})=>el.isConnected).forEach(({el,disabled})=>el.disabled=disabled);}}
  }
  function renderReport(doc,report) {const delivery=report?.delivery_status || doc.delivery_status,eligibility=report?.qualification_status || doc.eligibility,actions=report?.actions || [];const legacy=!!state.task?.legacy;const usable=eligibility==='eligible'&&delivery==='complete';    const tocState=report?.has_toc_field===true?'<span class="badge b-amber">未刷新 · 请在 Word 中更新目录</span>':report?.has_toc_field===false?'<span class="badge b-gray">无目录域</span>':'<span class="badge b-gray">未确认</span>';
    let html=legacy?'<div class="detail-section"><div class="callout"><strong>遗留任务 · 只读</strong>该任务由已下线的规则集引擎产生，仅可查看与下载历史产物；不能补传、不能重新修订。</div></div>':'';
    html+=`<div class="detail-section"><h3>业务结论</h3><dl class="detail-grid"><dt>合同资格</dt><dd>${badge(eligibility || 'pending')}</dd><dt>上传状态</dt><dd>${badge(doc.upload_status,doc.upload_status==='pending'?'待上传':null)}</dd><dt>处理状态</dt><dd>${badge(doc.job_status)}</dd><dt>交付完整性</dt><dd>${badge(delivery)}</dd><dt>目录状态</dt><dd>${tocState}</dd><dt>可直接使用</dt><dd>${usable?badge('complete','已通过交付校验'):badge('incomplete','不可认定')}</dd></dl><div class="callout"><strong>${esc(docReason(doc))}</strong>${(delivery||'').startsWith('evaluation_')?'本次为合同修订（评测）：产物为评测修改版，不能作为正式合同；正式写入未开启。':!usable?'报告与诊断文件不作为最终合同。':''}</div></div>`;    if(report) {html+=`<div class="detail-section"><h3>资格证据</h3>${eligibilityEvidenceHTML(report)||'<p class="subnote">报告未提供资格证据。</p>'}</div>`;
      html+=revisionSection(doc,report);
      html+=downloadSection(doc,delivery,usable||delivery==='complete_with_exceptions');
      const summary=report.user_summary;
      if(summary&&Array.isArray(summary.issues)&&summary.issues.length){html+=unresolvedIssuesHTML(report,summary);}
      const rows=changedClauses(report,doc);
      if(rows.length)html+=`<div class="detail-section"><h3>条款改动对照 · ${rows.length} 处</h3>${rows.map(clauseRow).join('')}</div>`;
      if(actions.length)html+=`<div class="detail-section"><h3>规则动作与条款证据 · ${actions.length} 项</h3>${actions.map(a=>`<details class="action-evidence"><summary>${esc(a.description || a.title || a.name || '规则动作')} ${badge(a.status)}</summary>${a.failure_reason?`<p>${esc(reason(a.failure_reason))}</p>`:''}${(a.candidates || []).map(c=>`<div class="candidate"><p>${badge(c.status)} ${esc(reason(c.failure_reason || c.reason))}</p>${proof(c)}</div>`).join('')}</details>`).join('')}</div>`;
      const exceptions=Array.isArray(report.exceptions)?report.exceptions:[];
      if(exceptions.length)html+=`<div class="detail-section"><h3>未自动修改的条款 · ${exceptions.length} 项</h3>${exceptions.map(e=>`<p><strong>${esc(e.description || e.title || e.action_id || '条款')}</strong> · ${esc(reason(e.reason))}</p>`).join('')}<p class="subnote">以上条款未自动修改（证据不足或原文与指引旧文不一致），请人工核对。</p></div>`;
    }else html+='<div class="detail-section"><h3>合同报告</h3><p>报告尚未生成。可刷新任务状态后再查看；未上传文件需先补传。</p></div>';
    $('detail-body').innerHTML=html;
  }
  function downloadSection(doc,delivery,usable){const downloads=doc.downloads || {};const evaluation=(delivery||'').startsWith('evaluation_');const kinds=[['report_md','Markdown 报告'],['report_json','JSON 报告'],['final','最终版 DOCX'],['selected_final',`按人工选择的${selectedContractLabel(doc)} DOCX`],['redline','修订版 DOCX（引擎全量痕迹）'],['selected_redline','修订版 DOCX（仅人工接受）'],['working_final','工作文件（未完成）· 合同'],['working_redline','工作文件（未完成）· 修订痕迹'],['evaluation_redline','评测修订痕迹 DOCX'],['evaluation_final','评测修改版 DOCX']].filter(([kind])=>downloads[kind]&&!(kind==='final'&&!usable));let html='<div class="detail-section"><h3>报告与文件下载</h3><div class="detail-actions">';html+=kinds.map(([kind,title])=>`<button class="btn ${kind.startsWith('report_')?'btn-primary':''} btn-sm" data-download="${kind}">${title}</button>`).join('')||'<p class="subnote">暂无可下载的报告或文件。</p>';html+='</div><p class="subnote">'+((downloads.working_final||downloads.working_redline)?'工作文件（未完成）是未完成交付，不能作为最终合同；':'')+(evaluation?'评测文件不能作为正式合同。':'')+'</p></div>';return html;}
  function eligibilityEvidenceHTML(report) {const src=report.qualification || report.eligibility || {};const items=[];const quote=src.fund_type_quote;if(quote)items.push(proof(quote));if(src.fund_type_basis)items.push(`<p class="subnote">${esc(src.fund_type_basis)}</p>`);else if(src.basis)items.push(`<p class="subnote">依据：${esc(src.basis)}</p>`);const extra=report.qualification?.evidence || report.eligibility?.evidence || report.qualification_evidence || [];const list=Array.isArray(extra)?extra:[extra];for(const item of list)items.push(proof(item));return items.join('');}
  async function showDetail(doc) {if(!doc)return;reviewDecisionsSave();state.review=null;state.tokens.review=(state.tokens.review||0)+1;const t=ticket('detail'),id=state.selected;state.detail=doc;state.focusReturn=document.activeElement;$('detail-title').textContent=doc.name;$('detail-body').innerHTML='<div class="empty">正在读取合同状态与报告…</div>';$('detail-overlay').hidden=false;document.querySelector('.app').inert=true;$('close-detail').focus();try{const report=doc.report_url?await json(doc.report_url):null;if(!current(t)||state.selected!==id||$('detail-overlay').hidden)return;renderReport(doc,report);}catch(e){if(current(t)){$('detail-body').innerHTML='<div class="empty">报告暂无法读取，请关闭后重试。</div>';errorNotice(e);}}}
  function closeDetail() {reviewDecisionsSave();state.review=null;state.tokens.review=(state.tokens.review||0)+1;if(!$('detail-overlay').hidden){$('detail-overlay').hidden=true;document.querySelector('.app').inert=false;state.focusReturn?.focus();}state.tokens.detail=(state.tokens.detail || 0)+1;state.detail=null;$('detail-body').replaceChildren();$('detail-title').textContent='';}
  function resetWorkspace(){document.dispatchEvent(new Event('fundlex:identity-reset'));$('toast').replaceChildren();$('toast').hidden=true;showToast.recent={};$('help-overlay').hidden=true;$('notification-toggle').setAttribute('aria-expanded','false');notifications.length=0;taskStatuses=new Map();$('notification-panel').hidden=true;renderNotifications();state.epoch++;state.importSession++;state.controllers.forEach(c=>c.abort());state.controllers.clear();state.tokens={};state.selected=null;state.task=null;state.tasks=[];state.tasksLoaded=false;state.tasksFailed=false;state.cap=null;state.overviewStats=null;state.taskGuides=null;state.imports=[];state.recover=null;state.createKey=null;state.uploadToken=null;state.uploading=false;state.uploadProgress=null;state.replaceTarget=null;state.reviewDocs=null;state.reviewDocsTask=null;state.reviewDocsKey='';state.review=null;state.reviewDecisions=new Map();state.selectionBusy=null;state.guideDismissed=false;$('user-rows').replaceChildren();for(const id of ['new-user-name','new-user-display','new-user-password','pwd-old','pwd-new','pwd-confirm','register-password','register-confirm'])$(id).value='';$('password-view').hidden=true;for(const id of ['user-create-btn','pwd-submit'])$(id).disabled=false;for(const id of ['user-create-error','pwd-error']){$(id).textContent='';$(id).hidden=true;}state.taskPage=state.importPage=state.docPage=1;state.taskDocs=[];closeDetail();$('task-rows').innerHTML=emptyRow(6,'正在读取任务');$('doc-rows').innerHTML=emptyRow(7,'请选择当前身份的任务');$('task-pagination').replaceChildren();$('doc-pagination').replaceChildren();$('capability-details').replaceChildren();$('doc-scope-note').hidden=true;$('task-name').value='';$('detail-title').textContent='';$('doc-scope').textContent='';$('doc-reason-filter').innerHTML='<option value="">全部原因</option>';$('upload-message').textContent='选择文件后检查清单，开始上传任务。';resetGuides();$('file-picker').value='';$('folder-picker').value='';$('replace-picker').value='';for(const id of ['task-search','import-search','doc-search'])$(id).value='';for(const id of ['task-filter','task-guide-filter','import-filter','doc-upload-filter','doc-qualification-filter','doc-completeness-filter','doc-status-filter','doc-reason-filter','doc-sort'])$(id).value='';renderOverview(null);renderTaskGuideFilter();renderTask();renderImport();renderTopbarTitle(state.view);renderBreadcrumb(state.view);renderFooter();}
  function identityChanged(){resetWorkspace();hideLogin();try{localStorage.setItem('fundlex-dev-user',owner());}catch{}clearTimeout(identityChanged.timer);identityChanged.timer=setTimeout(()=>refresh(true),350);}
  async function loadMe(){const user=await json('/api/auth/me');setAuthSession(state.auth.token,user);return user;}
  function handleSessionExpired(){if(state.auth.mode!=='password')return;if(!state.auth.token&&!state.auth.user)return;clearAuthSession();resetWorkspace();showLogin('登录状态已失效，请重新登录。');}
  async function submitLogin(event){event.preventDefault();const username=$('login-username').value.trim(),password=$('login-password').value,button=$('login-submit'),box=$('login-error');if(!username||!password){box.textContent='请输入用户名和密码。';box.hidden=false;return;}button.disabled=true;box.hidden=true;try{const response=await fetch(appPath('/api/auth/login'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password}),cache:'no-store'});let payload=null;try{payload=await response.json();}catch{}if(!response.ok){const detail=payload&&typeof payload.detail==='string'?payload.detail:'';throw new Error(response.status===401?'用户名或密码不正确。':response.status===403?'账号已被禁用，请联系管理员。':response.status===404?'当前环境未启用账号登录。':detail||'登录未完成，请重试。');}if(!payload||!payload.token||!payload.user)throw new Error('登录响应未通过格式校验，请重试。');state.auth.mode='password';setAuthSession(payload.token,payload.user);hideLogin();await refresh(true);}catch(e){if(e&&e.name!=='AbortError'){box.textContent=e.message||'登录未完成，请重试。';box.hidden=false;}}finally{button.disabled=false;}}
  async function logout(){const token=state.auth.token;clearAuthSession();resetWorkspace();showLogin('已退出登录。');try{await fetch(appPath('/api/auth/logout'),{method:'POST',headers:token?{'Authorization':`Bearer ${token}`}:{},cache:'no-store'});}catch{}}
  function openPasswordDialog(){const view=$('password-view');if(!view||!state.auth.user)return;view.hidden=false;document.querySelector('.app').inert=true;$('pwd-error').hidden=true;$('pwd-old').value='';$('pwd-new').value='';$('pwd-confirm').value='';$('pwd-old').focus();}
  function closePasswordDialog(){const view=$('password-view');if(!view||view.hidden)return;view.hidden=true;if($('login-view').hidden)document.querySelector('.app').inert=false;}
  async function submitPasswordChange(event){event.preventDefault();const epoch=state.epoch;const oldP=$('pwd-old').value,newP=$('pwd-new').value,confirmP=$('pwd-confirm').value,box=$('pwd-error'),button=$('pwd-submit');const fail=message=>{box.textContent=message;box.hidden=false;};box.hidden=true;if(!oldP||!newP||!confirmP)return fail('请填写全部密码字段。');if(newP.length<8)return fail('新密码至少 8 位。');if(newP!==confirmP)return fail('两次输入的新密码不一致。');button.disabled=true;try{const response=await fetch(appPath('/api/auth/password'),{method:'POST',headers:{'Content-Type':'application/json',...(state.auth.token?{'Authorization':`Bearer ${state.auth.token}`}:{})},body:JSON.stringify({old_password:oldP,new_password:newP}),cache:'no-store'});if(!identityCurrent(epoch))return;let payload=null;try{payload=await response.json();}catch{}if(!identityCurrent(epoch))return;if(!response.ok){const detail=payload&&typeof payload.detail==='string'?payload.detail:'';if(response.status===401&&detail==='current password is incorrect')return fail('当前密码不正确。');if(response.status===401){closePasswordDialog();handleSessionExpired();return;}return fail(detail||'修改失败，请稍后重试。');}closePasswordDialog();toast('密码已更新，其它设备需重新登录。');}catch{if(!identityCurrent(epoch))return;fail('无法连接本地服务，请稍后重试。');}finally{if(identityCurrent(epoch))button.disabled=false;}}
  async function submitRegister(event){event.preventDefault();const username=$('register-username').value.trim(),display=$('register-display').value.trim(),password=$('register-password').value,confirm=$('register-confirm').value,box=$('register-error'),button=$('register-submit');const fail=message=>{box.textContent=message;box.hidden=false;};box.hidden=true;if(username.length<3)return fail('用户名至少 3 位。');if(!/^[A-Za-z0-9_.-]+$/.test(username))return fail('用户名只能使用字母、数字或 _ . -。');if(password.length<8)return fail('密码至少 8 位。');if(password!==confirm)return fail('两次输入的密码不一致。');button.disabled=true;try{const response=await fetch(appPath('/api/auth/register'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password,display_name:display}),cache:'no-store'});let payload=null;try{payload=await response.json();}catch{}if(!response.ok){const detail=payload&&typeof payload.detail==='string'?payload.detail:'';if(response.status===409)return fail('该用户名已被注册，请更换。');if(response.status===403)return fail('当前环境未开放注册。');if(response.status===422)return fail('输入不符合要求，请检查用户名与密码。');return fail(detail||'注册未完成，请稍后重试。');}state.auth.mode='password';setAuthSession(payload.token,payload.user);resetWorkspace();hideLogin();refresh(true);}catch{fail('无法连接本地服务，请稍后重试。');}finally{button.disabled=false;}}
  async function loadUsers(){const t=ticket('users'),rows=$('user-rows');rows.setAttribute('aria-busy','true');try{const payload=await json('/api/admin/users');if(!current(t))return;const users=(payload&&payload.users)||[];rows.innerHTML=users.map(u=>{const ts=u.created_at>1e12?u.created_at:u.created_at*1000;const self=state.auth.user&&u.id===state.auth.user.id;return `<tr><td><span class="filename">${esc(u.username)}</span>${self?'<span class="row-sub">当前登录账号</span>':''}</td><td>${esc(u.display_name||'—')}</td><td>${u.role==='admin'?'管理员':'成员'}</td><td>${u.disabled?badge('failed','已禁用'):badge('succeeded','正常')}</td><td>${esc(new Date(ts).toLocaleString('zh-CN'))}</td><td>${self?'':`<button class="btn-link" data-user-toggle="${esc(u.id)}" data-user-disabled="${u.disabled?1:0}">${u.disabled?'启用':'禁用'}</button>`}</td></tr>`;}).join('')||emptyRow(6,'当前没有可显示的账号');}catch(e){if(current(t)){rows.innerHTML=emptyRow(6,'账号列表暂未加载，请刷新后重试');errorNotice(e);}}finally{if(current(t))rows.removeAttribute('aria-busy');}}
  async function toggleUser(id,disabled){const t=ticket('users');try{const response=await fetch(appPath(`/api/admin/users/${encodeURIComponent(id)}/disable`),{method:'POST',headers:{'Content-Type':'application/json',...(state.auth.token?{'Authorization':`Bearer ${state.auth.token}`}:{})},body:JSON.stringify({disabled}),cache:'no-store'});if(!identityCurrent(t.epoch))return;if(response.status===401){handleSessionExpired();return;}if(!response.ok){let detail='';try{const p=await response.json();detail=typeof p.detail==='string'?p.detail:'';}catch{}throw new Error(detail||'操作未完成，请稍后重试。');}if(!current(t))return;toast(disabled?'账号已禁用，其登录会话已失效。':'账号已启用。');await loadUsers();}catch(e){if(current(t))errorNotice(e);}}
  async function createUser(){const epoch=state.epoch;const username=$('new-user-name').value.trim(),display=$('new-user-display').value.trim(),role=$('new-user-role').value,password=$('new-user-password').value,box=$('user-create-error'),button=$('user-create-btn');const fail=message=>{box.textContent=message;box.hidden=false;};box.hidden=true;if(username.length<3)return fail('用户名至少 3 位。');if(!/^[A-Za-z0-9_.-]+$/.test(username))return fail('用户名只能使用字母、数字或 _ . -。');if(password.length<8)return fail('初始密码至少 8 位。');button.disabled=true;try{const response=await fetch(appPath('/api/admin/users'),{method:'POST',headers:{'Content-Type':'application/json',...(state.auth.token?{'Authorization':`Bearer ${state.auth.token}`}:{})},body:JSON.stringify({username,password,display_name:display,role}),cache:'no-store'});if(!identityCurrent(epoch))return;if(response.status===401){handleSessionExpired();return;}if(!response.ok){let detail='';try{const p=await response.json();detail=typeof p.detail==='string'?p.detail:'';}catch{}if(!identityCurrent(epoch))return;if(response.status===409)return fail('该用户名已存在。');if(response.status===422)return fail('输入不符合要求，请检查用户名与密码。');return fail(detail||'创建未完成，请稍后重试。');}$('new-user-name').value='';$('new-user-display').value='';$('new-user-password').value='';$('new-user-role').value='member';toast('账号已创建，请将用户名与初始密码告知本人。');await loadUsers();}catch{if(!identityCurrent(epoch))return;fail('无法连接本地服务，请稍后重试。');}finally{if(identityCurrent(epoch))button.disabled=false;}}
  const GUIDE_STATUSES={uploaded:'待解析',parsing:'解析中',parsed:'已解析',validated:'已校验',parse_failed:'解析失败',failed:'解析失败',released:'已发布',archived:'已归档'};
  const GUIDE_QUALIFICATION={not_run:'未运行',frozen_builtin:'内置冻结',passed:'已通过',qualified:'已通过',failed:'未通过'};
  const GUIDE_ENABLEABLE=['parsed','released'],GUIDE_PARSEABLE=['uploaded','parse_failed','parsed','failed'],GUIDE_RULES_READY=['parsed','validated','released'];
  const guideStatusLabel=value=>GUIDE_STATUSES[value] || '未确认';
  const guideTime=value=>value?new Date(value>1e12?value:value*1000).toLocaleString('zh-CN'):'—';
  const shortHash=value=>value?String(value).slice(0,12):'—';
  const guideKind=item=>item.built_in?'<span class="badge b-gray">内置</span>':'<span class="badge b-blue">自定义</span>';
  const guideCurrentFlag=item=>item.current?'<span class="badge b-green">当前使用</span>':'';
  const guideByName=id=>(state.guides || []).find(item=>item.id===id) || null;
  const guideReady=()=>!!state.cap?.engine?.guide&&state.cap.engine.delivery_mode==='formal';
  const guideOps=counts=>{const value=counts&&typeof counts==='object'?counts:{};return [['新增',value.append],['替换',value.replace],['删除',value.delete],['无需修改',value.noop]].map(([label,count])=>`${label} ${Number(count) || 0}`).join(' · ');};
  function renderGuideBinding() {const box=$('guide-binding');if(!box)return;const cap=state.cap,guide=cap?.engine?.guide || null;box.hidden=false;if(!cap){box.className='guide-binding';box.textContent='当前指引尚未加载，请刷新重试。';return;}
    if(guide&&guideReady()){box.className='guide-binding';box.innerHTML=`当前指引：<strong>${esc(guide.filename)}</strong>（规则 ${guide.groups || 0} 条 · ${esc(guideStatusLabel(guide.status))}）${guideKind(guide)}`;return;}
    box.className='guide-binding guide-binding-warning';box.innerHTML='当前指引不可用：暂时不能创建任务。请先到 <button type="button" class="btn-link" data-nav="guide">指引配置</button> 启用可用指引，再刷新本页。';}
  function resetGuides() {state.guides=null;state.guidesFailed=false;state.guideBusy=null;state.guideUploading=false;clearTimeout(state.guideTimer);state.guideTimer=null;const input=$('guide-file');if(input)input.value='';const name=$('guide-file-name');if(name)name.textContent='尚未选择文件';const button=$('guide-upload-btn');if(button)button.disabled=true;const message=$('guide-upload-message');if(message)message.textContent='解析失败可在列表中查看问题并重新解析。';$('guide-rows').innerHTML=emptyRow(7,'正在读取指引列表');$('guide-current-body').textContent='正在读取当前指引…';$('guide-current-flags').replaceChildren();$('guide-list-state').textContent='';$('guide-reset-btn').disabled=true;$('guide-reset-btn').title='恢复内置指引并用于之后创建的任务';closeGuidePanel();}
  async function loadGuides(quiet=false) {if(state.auth.mode==='password'&&!state.auth.token)return;const t=ticket('guide'),rows=$('guide-rows');if(!quiet){rows.setAttribute('aria-busy','true');$('guide-list-state').textContent='正在读取指引列表…';}
    try{const payload=await json('/api/guides');if(!current(t))return;state.guides=Array.isArray(payload.items)?payload.items:[];state.guidesFailed=false;renderGuides();}
    catch(e){if(!current(t))return;state.guides=null;state.guidesFailed=true;rows.innerHTML=emptyRow(7,e.code===404?'当前环境未提供指引配置接口':'指引列表暂未加载，请检查连接后刷新');$('guide-list-state').textContent='';$('guide-current-body').innerHTML=`<p class="subnote">${esc(e.code===404?'当前环境未提供指引配置接口，或该账号暂不可访问；可刷新重试。':'当前指引暂不可读；请刷新重试。')}</p>`;$('guide-current-flags').replaceChildren();$('guide-reset-btn').disabled=true;if(e.code!==404)errorNotice(e);}
    finally{if(current(t))rows.removeAttribute('aria-busy');}}
  function renderGuides() {const items=state.guides || [],current=items.find(item=>item.current) || null,busy=!!state.guideBusy;
    $('guide-current-flags').innerHTML=current?guideKind(current)+guideCurrentFlag(current):'';
    $('guide-current-body').innerHTML=current?`<dl class="detail-grid"><dt>文件名</dt><dd><span class="filename" title="${esc(current.filename)}">${esc(current.filename)}</span></dd><dt>版本</dt><dd>${esc(current.id)}</dd><dt>状态</dt><dd>${badge(current.status, GUIDE_STATUSES[current.status])}</dd><dt>规则条数</dt><dd>${current.groups} 条</dd><dt>规则哈希</dt><dd title="${esc(current.rules_sha256 || '')}">${current.rules_sha256?esc(shortHash(current.rules_sha256))+'…':'—'}</dd><dt>资格状态</dt><dd>${esc(GUIDE_QUALIFICATION[current.qualification_status] || current.qualification_status || '未运行')}</dd></dl>`:'<p class="subnote">尚未确定当前指引。请刷新列表，或上传并启用一个已解析的自定义指引。</p>';
    $('guide-rows').innerHTML=items.map(item=>{const enable=GUIDE_ENABLEABLE.includes(item.status),parse=!item.built_in&&GUIDE_PARSEABLE.includes(item.status),rules=GUIDE_RULES_READY.includes(item.status);
      return `<tr><td><span class="filename" title="${esc(item.filename)}">${esc(item.filename)}</span><span class="row-sub">${esc(item.id)}</span></td><td>${badge(item.status, GUIDE_STATUSES[item.status])}</td><td>${item.groups} 条</td><td>${item.issues} 项</td><td>${guideKind(item)}${guideCurrentFlag(item)}</td><td>${esc(guideTime(item.created_at))}</td><td><div class="guide-actions"><button class="btn-link" data-guide-enable="${esc(item.id)}" ${busy||item.current||!enable?'disabled':''} title="${item.current?'该指引当前正在使用':enable?'新任务改用该指引':'解析完成后才能启用'}">启用</button><button class="btn-link" data-guide-parse="${esc(item.id)}" ${busy||!parse?'disabled':''} title="${item.built_in?'内置指引无需重新解析':parse?'重新提交解析并自动修复解析问题':'当前状态不能重新解析'}">重新解析</button><button class="btn-link" data-guide-issues="${esc(item.id)}" ${busy?'disabled':''}>查看问题</button><button class="btn-link" data-guide-rules="${esc(item.id)}" ${busy||!rules?'disabled':''} title="${rules?'查看解析出的规则':'解析完成后可查看规则'}">查看规则</button><button class="btn-link" data-guide-source="${esc(item.id)}" ${busy||item.built_in?'disabled':''} title="${item.built_in?'内置指引不提供原件下载':'下载上传的指引原件'}">下载原件</button></div></td></tr>`;}).join('') || emptyRow(7,'还没有可用指引');
    $('guide-list-state').textContent=items.length?`共 ${items.length} 个版本 · 上传后自动解析；启用只影响之后创建的任务。`:'';
    $('guide-reset-btn').disabled=busy||!current||!!current.built_in;
    $('guide-reset-btn').title=current&&current.built_in?'当前已使用内置指引':'恢复内置指引并用于之后创建的任务';
    guidePolling();}
  function guidePolling() {clearTimeout(state.guideTimer);state.guideTimer=null;if(state.view!=='guide')return;if(!(state.guides || []).some(item=>item.status==='uploaded'||item.status==='parsing'))return;const epoch=state.epoch;state.guideTimer=setTimeout(()=>{if(identityCurrent(epoch)&&state.view==='guide')loadGuides(true);},4000);}
  async function enableGuide(id) {if(state.guideBusy)return;state.guideBusy=id;renderGuides();const t=ticket('guide-action'),item=guideByName(id);try{const payload=await json('/api/settings/guide',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({version_id:id})});if(!current(t))return;if(Array.isArray(payload.available))state.guides=payload.available;state.guideBusy=null;renderGuides();toast(`已启用指引：${item?item.filename:id}`);await loadCapabilities();}
    catch(e){if(!current(t))return;state.guideBusy=null;renderGuides();errorNotice(e,'指引切换未完成：');}}
  async function resetToBuiltinGuide() {if(state.guideBusy)return;state.guideBusy='reset';renderGuides();const t=ticket('guide-action');try{const payload=await json('/api/settings/guide',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({version_id:null})});if(!current(t))return;if(Array.isArray(payload.available))state.guides=payload.available;state.guideBusy=null;renderGuides();toast('已恢复内置指引，之后创建的任务使用内置指引。');await loadCapabilities();}
    catch(e){if(!current(t))return;state.guideBusy=null;renderGuides();errorNotice(e,'恢复内置指引未完成：');}}
  async function reparseGuide(id) {if(state.guideBusy)return;state.guideBusy=id;renderGuides();const t=ticket('guide-action');try{const payload=await json(`/api/guides/${encodeURIComponent(id)}/parse`,{method:'POST'});if(!current(t))return;const version=payload&&payload.version;if(version&&state.guides)state.guides=state.guides.map(item=>item.id===version.id?{...item,...version}:item);state.guideBusy=null;renderGuides();toast('已提交重新解析，稍后刷新查看状态。');}
    catch(e){if(!current(t))return;state.guideBusy=null;renderGuides();errorNotice(e,'重新解析未完成：');}}
  function downloadGuideSource(id) {const item=guideByName(id);if(!item||item.built_in)return;download(`/api/guides/${encodeURIComponent(id)}/source`,item.filename || `${id}.docx`);}
  async function uploadGuide() {const input=$('guide-file'),file=input&&input.files?input.files[0]:null,message=$('guide-upload-message');if(!file||state.guideUploading)return;
    if(!/\.docx$/i.test(file.name)){message.textContent='仅支持 DOCX 指引文件，请重新选择。';return;}
    const limit=state.cap&&state.cap.upload_limits?state.cap.upload_limits.max_file_bytes:0;if(limit&&file.size>limit){message.textContent=`文件超过单文件 ${size(limit)} 限制，请压缩后再上传。`;return;}
    const epoch=state.epoch;state.guideUploading=true;$('guide-upload-btn').disabled=true;const form=new FormData();form.append('file',file,file.name);message.textContent='正在上传指引原件…';
    try{const payload=await uploadRequest('/api/guides',form,(loaded,total)=>{if(identityCurrent(epoch))message.textContent=`正在上传指引原件 · ${Math.min(100,Math.round(100*loaded/total))}%`;});if(!identityCurrent(epoch))return;const version=payload&&payload.version;message.textContent=`已上传 ${version&&version.filename?version.filename:file.name}；解析会自动进行，完成后在「可用指引」中查看状态并启用。`;input.value='';$('guide-file-name').textContent='尚未选择文件';toast('指引已上传，正在自动解析');await loadGuides();}
    catch(e){if(!identityCurrent(epoch)||e.name==='AbortError')return;message.textContent=e.code===415?'仅支持 DOCX 指引文件，请重新选择。':e.code===413?`文件超过接收限制${limit?`（单文件 ≤ ${size(limit)}）`:''}。`:e.message || '上传未完成，请重试。';errorNotice(e,'指引上传失败：');}
    finally{if(identityCurrent(epoch)){state.guideUploading=false;$('guide-upload-btn').disabled=!(input.files&&input.files.length);}}}
  function openGuidePanel(id,mode) {const item=guideByName(id);if(!item)return;const t=ticket('guide-detail');state.guideDetail={id,mode};state.focusReturn=document.activeElement;$('guide-overlay-title').textContent=item.filename;$('guide-overlay-body').innerHTML='<div class="empty">正在读取指引详情…</div>';$('guide-overlay').hidden=false;document.querySelector('.app').inert=true;$('guide-overlay-close').focus();loadGuidePanel(item,mode,t);}
  async function loadGuidePanel(item,mode,t) {const path=mode==='rules'?`/api/guides/${encodeURIComponent(item.id)}/rules`:`/api/guides/${encodeURIComponent(item.id)}`;
    try{const data=await json(path);if(!current(t)||$('guide-overlay').hidden)return;renderGuidePanel(item,data,mode);}
    catch(e){if(!current(t)||$('guide-overlay').hidden)return;$('guide-overlay-body').innerHTML=`<div class="empty">${esc(mode==='rules'&&e.code===404?'规则尚未生成：解析完成后可查看。':'指引详情暂无法读取，请关闭后重试。')}</div>`;if(e.code!==404)errorNotice(e);}}
  function guideRulesOverview(doc) {const groups=Array.isArray(doc&&doc.groups)?doc.groups:[];return groups.map(group=>{const counts={append:0,replace:0,delete:0,noop:0};for(const operation of Array.isArray(group&&group.operations)?group.operations:[])if(operation&&typeof operation.op==='string'&&operation.op in counts)counts[operation.op]+=1;return {rule_id:group&&group.rule_id,title:group&&group.title,section_hint:group&&group.section_hint,operations:counts};});}
  const GUIDE_ISSUE_HINTS={
    GUIDE_SLOT_NOT_IN_TEXT:'核对新文中是否包含槽位 token；修正指引原文后重新解析（自动修复）。',
    GUIDE_GROUP_INVALID:'检查该规则组的规则编号、操作与文本字段是否完整，修正后重新解析。',
    GUIDE_PARAGRAPH_RANGE_INVALID:'检查来源段落编号是否超出指引正文范围，修正后重新解析。',
    GUIDE_PARAGRAPH_ORDER:'来源段落编号需按升序且不重复，修正后重新解析。',
    GUIDE_GROUP_EMPTY:'该来源段落未生成有效规则组，补充或调整来源编号后重新解析。'
  };
  function guideIssueHint(code){return GUIDE_ISSUE_HINTS[code]||'核对问题位置和证据原文；如为指引原件问题，修正后点击“重新解析（自动修复）”。';}
  function guideIssueDetails(code,rule,detail,paragraphs=[],evidence='',open=false){
    const position=[rule?`规则 ${rule}`:'未提供规则编号',Array.isArray(paragraphs)&&paragraphs.length?`段落 ${paragraphs.join('、')}`:''].filter(Boolean).join(' · ');
    return `<li><details class="guide-issue" ${open?'open':''}><summary><code>${esc(code||'ISSUE')}</code>${detail?` · ${esc(String(detail).slice(0,80))}`:''}</summary><dl class="guide-issue-grid"><dt>问题位置</dt><dd>${esc(position||'未提供')}</dd><dt>失败原因</dt><dd>${esc(detail||'未提供详细原因')}</dd><dt>修复建议</dt><dd>${esc(guideIssueHint(code))}</dd></dl>${evidence?`<details class="guide-quote"><summary>证据原文</summary><p>${esc(evidence)}</p></details>`:''}</details></li>`;
  }
  function guideIssuesHTML(issues,item) {const value=issues&&typeof issues==='object'?issues:{},errors=Array.isArray(value.errors)?value.errors:[],warnings=Array.isArray(value.warnings)?value.warnings:[],gaps=Array.isArray(value.coverage_gaps)?value.coverage_gaps:[],findings=value.verification&&Array.isArray(value.verification.findings)?value.verification.findings:[];let html='';
    if(value.error_code&&!errors.length)html+=`<p class="subnote">最近一次解析错误：<code>${esc(value.error_code)}</code>${value.attempts?` · 已尝试 ${esc(String(value.attempts))} 次`:''}</p>`;
    if(errors.length)html+=`<h4 class="guide-issue-head">校验错误 · ${errors.length} 项</h4><ul class="guide-issues">${errors.map(entry=>guideIssueDetails(entry&&entry.code,entry&&entry.rule_id,entry&&entry.detail,[],'',true)).join('')}</ul>`;
    if(warnings.length)html+=`<h4 class="guide-issue-head">校验警告 · ${warnings.length} 项</h4><ul class="guide-issues">${warnings.map(entry=>guideIssueDetails(entry&&entry.code,entry&&entry.rule_id,entry&&entry.detail)).join('')}</ul>`;
    if(gaps.length)html+=`<h4 class="guide-issue-head">未覆盖段落 · ${gaps.length} 处</h4><ul class="guide-issues">${gaps.map(index=>guideIssueDetails('GUIDE_COVERAGE_GAP','', '该段未被任何规则组引用', [index])).join('')}</ul>`;
    if(findings.length)html+=`<h4 class="guide-issue-head">独立核验发现 · ${findings.length} 项</h4><ul class="guide-issues">${findings.map(finding=>guideIssueDetails(finding&&finding.kind?finding.kind:'FINDING',finding&&finding.rule_id,finding&&finding.description,Array.isArray(finding&&finding.paragraphs)?finding.paragraphs:[],finding&&finding.evidence_quote,true)).join('')}</ul>`;
    if(!html)html='<p class="subnote">尚未解析，或解析未发现问题。</p>';
    if(value.clean===true)html+='<p class="subnote">最近一次解析已通过确定性校验与独立核验。</p>';
    if(item&&!item.built_in&&GUIDE_PARSEABLE.includes(item.status))html+=`<div class="guide-issue-actions"><button class="btn btn-sm btn-primary" type="button" data-guide-reparse="${esc(item.id)}">重新解析（自动修复）</button><span class="subnote">会重新调用模型核对并修复解析问题，消耗调用额度；修正指引原件后再解析效果更好。</span></div>`;
    return html;}
  function renderGuidePanel(item,data,mode) {const overview=mode==='rules'?guideRulesOverview(data):(Array.isArray(data.rules_overview)?data.rules_overview:[]),issues=mode==='rules'?(data&&data.validation)||{}:(data.issues_detail||{}),qualification=data&&data.qualification_status;
    let html=`<div class="detail-section"><h3>指引信息</h3><dl class="detail-grid"><dt>版本</dt><dd>${esc(item.id)}</dd><dt>状态</dt><dd>${badge(item.status, GUIDE_STATUSES[item.status])}</dd><dt>类型</dt><dd>${guideKind(item)}${guideCurrentFlag(item)}</dd><dt>规则条数</dt><dd>${item.groups} 条</dd><dt>规则哈希</dt><dd title="${esc(item.rules_sha256 || '')}">${esc(shortHash(item.rules_sha256))}</dd><dt>创建时间</dt><dd>${esc(guideTime(item.created_at))}</dd><dt>更新时间</dt><dd>${esc(guideTime(item.updated_at))}</dd>${qualification?`<dt>资格状态</dt><dd>${esc(GUIDE_QUALIFICATION[qualification] || qualification)}</dd>`:''}</dl><p class="subnote">任务创建时绑定该版本与规则哈希；之后的修改不影响已创建任务。</p></div>`;
    html+=`<div class="detail-section"><h3>规则概览 · ${overview.length} 项</h3>${overview.length?`<div class="table-wrap"><table class="table" style="min-width:520px"><thead><tr><th>规则</th><th>标题</th><th>适用章节</th><th>操作</th></tr></thead><tbody>${overview.map(rule=>`<tr><td>${esc(rule&&rule.rule_id?rule.rule_id:'—')}</td><td>${esc(rule&&rule.title?rule.title:'—')}</td><td>${esc(rule&&rule.section_hint?rule.section_hint:'—')}</td><td class="guide-ops">${guideOps(rule&&rule.operations)}</td></tr>`).join('')}</tbody></table></div>`:'<p class="subnote">暂无规则概览；解析完成后生成。</p>'}</div>`;
    html+=`<div class="detail-section"><h3>解析问题</h3>${guideIssuesHTML(issues,item)}</div>`;
    $('guide-overlay-body').innerHTML=html;}
  function closeGuidePanel() {const overlay=$('guide-overlay');if(!overlay||overlay.hidden)return;overlay.hidden=true;if($('login-view').hidden&&$('password-view').hidden)document.querySelector('.app').inert=false;state.tokens['guide-detail']=(state.tokens['guide-detail'] || 0)+1;state.guideDetail=null;$('guide-overlay-body').replaceChildren();$('guide-overlay-title').textContent='';if(state.focusReturn){state.focusReturn.focus();state.focusReturn=null;}}
  document.addEventListener('click',e=>{const crumb=e.target.closest('[data-crumb]');if(crumb){e.preventDefault();go(crumb.dataset.crumb);return;}const nav=e.target.closest('[data-nav]');if(nav){e.preventDefault();if(nav.dataset.nav==='settings'&&state.cap&&state.cap.auth_mode!=='dev'){notice('当前运行环境未开放开发设置。',true);return;}if(nav.dataset.nav==='import'&&(state.recover||!state.imports.length))newTask();else go(nav.dataset.nav);return;}const reviewAction=(e.target.closest('[data-action]')||{}).dataset?.action;if(reviewAction==='open-review'){openReview();return;}if(reviewAction==='accept-all'){generateSelected('accept');return;}if(reviewAction==='generate-selected'){generateSelected();return;}if(reviewAction==='review-close'){closeReview();return;}if(reviewAction==='review-accept-all'){setAllRevisions('accept');return;}if(reviewAction==='review-reject-all'){setAllRevisions('reject');return;}if(reviewAction==='review-prev'){switchReview(-1);return;}if(reviewAction==='review-next'){switchReview(1);return;}if(reviewAction==='download-selected'){const d=state.detail;if(d&&d.downloads&&d.downloads.selected_final)download(d.downloads.selected_final,`${d.name.replace(/\.docx$/i,'')}_selected_final.docx`);return;}const revItem=e.target.closest('[data-rev-item]');if(revItem){if(!e.target.closest('input,label'))focusRevision(Number(revItem.dataset.revItem));return;}const revNode=e.target.closest('#review-doc [data-rev]');if(revNode){if(!e.target.closest('a')){const entry=state.review?.revisions.find(r=>(r.revision_ids||[r.del_id,r.ins_id??Number(r.del_id)+1]).some(id=>String(id)===revNode.dataset.rev));if(entry)focusRevision(entry.del_id);}return;}const task=e.target.closest('[data-task]');if(task){selectTask(task.dataset.task);return;}const userToggle=e.target.closest('[data-user-toggle]');if(userToggle){toggleUser(userToggle.dataset.userToggle,userToggle.dataset.userDisabled!=='1');return;}const detail=e.target.closest('[data-detail]');if(detail){const [name,index]=detail.dataset.detail.split(':');showDetail(state.taskDocs[Number(index)]);return;}const replace=e.target.closest('[data-replace]');if(replace&&!state.uploading){state.replaceTarget=replace.dataset.replace;$('replace-picker').click();return;}const remove=e.target.closest('[data-remove]');if(remove&&!state.uploading){state.imports=state.imports.filter(f=>f.id!==remove.dataset.remove);state.createKey=null;renderImport();return;}const clearOne=e.target.closest('[data-clear-filter]');if(clearOne){const [scope,key]=clearOne.dataset.clearFilter.split(':');clearFilter(scope,key);return;}const clearAll=e.target.closest('[data-clear-filters]');if(clearAll){clearAllFilters(clearAll.dataset.clearFilters);return;}const page=e.target.closest('[data-page]');if(page){const name=page.dataset.page;state[`${name}Page`]+=page.dataset.dir==='next'?1:-1;if(name==='import')renderImport();else if(name==='task')loadTasks();else loadDocuments();return;}const dl=e.target.closest('[data-download]');if(dl&&state.detail){const kind=dl.dataset.download;const ext=kind.startsWith('report_')?(kind==='report_json'?'json':'md'):'docx';const label={final:'最终版',selected_final:'最终版（按人工选择）',redline:'修订版（引擎全量痕迹）',selected_redline:'修订版（仅人工接受）',working_final:'工作文件（未完成）',working_redline:'工作文件（未完成）修订痕迹'}[kind];download(state.detail.downloads[kind],`${state.detail.name.replace(/\.docx$/i,'')}${label?`_${label}`:''}.${ext}`);return;}const guideEnable=e.target.closest('[data-guide-enable]');if(guideEnable){enableGuide(guideEnable.dataset.guideEnable);return;}const guideParse=e.target.closest('[data-guide-parse]');if(guideParse){reparseGuide(guideParse.dataset.guideParse);return;}const guideReparse=e.target.closest('[data-guide-reparse]');if(guideReparse){closeGuidePanel();reparseGuide(guideReparse.dataset.guideReparse);return;}const guideIssues=e.target.closest('[data-guide-issues]');if(guideIssues){openGuidePanel(guideIssues.dataset.guideIssues,'issues');return;}const guideRules=e.target.closest('[data-guide-rules]');if(guideRules){openGuidePanel(guideRules.dataset.guideRules,'rules');return;}const guideSource=e.target.closest('[data-guide-source]');if(guideSource){downloadGuideSource(guideSource.dataset.guideSource);return;}const action=e.target.closest('[data-action]')?.dataset.action;if(!action)return;switch(action){case 'help-open':openHelp();break;case 'help-close':closeHelp();break;case 'notifications':{const panel=$('notification-panel');panel.hidden=!panel.hidden;$('notification-toggle').setAttribute('aria-expanded',String(!panel.hidden));if(!panel.hidden){notifications.forEach(n=>n.read=true);renderNotifications();}break;}case 'download-all':if(!state.task){notify('请先选择任务。',true);break;}if(document.querySelector('[data-action="download-all"]')?.disabled){notify('该任务尚无可下载的合同结果，请等待处理完成或先在“任务详情”确认产物。',true);break;}download(`${pathTask()}/download/all`,`${state.task.name}_全部结果.zip`);break;case 'new-task':newTask();break;case 'cancel-recover':if(state.uploading)break;state.importSession++;state.tokens.recovery=(state.tokens.recovery||0)+1;state.recover=null;state.imports=[];state.createKey=null;state.importPage=1;$('task-name').value='';resetImportStages();renderImport();go('task');break;case 'choose-files':$('file-picker').click();break;case 'choose-folder':$('folder-picker').click();break;case 'clear-import':if(!state.uploading){state.imports=[];state.createKey=null;state.importPage=1;state.uploadProgress=null;state.replaceTarget=null;resetImportStages(state.recover?(state.task?.id===state.recover.id?state.task:state.recover):null);renderImport();}break;case 'submit':submit();break;case 'dismiss-guide':state.guideDismissed=true;$('first-run-guide').setAttribute('hidden','');break;case 'refresh':refresh();break;case 'recover':recover();break;case 'toggle-pause':togglePause();break;case 'download-summary':if(state.task)download(state.task.summary_url,`${state.task.name}_结果总览.md`);else notice('请先选择任务。',true);break;case 'export-results':exportResults();break;case 'export-pending':exportPending();break;case 'users-refresh':loadUsers();break;case 'user-create':createUser();break;case 'guide-refresh':loadGuides();break;case 'guide-reset':resetToBuiltinGuide();break;case 'guide-choose':$('guide-file').click();break;case 'guide-upload':uploadGuide();break;}});
  for(const id of ['file-picker','folder-picker'])$(id).addEventListener('change',e=>{addFiles([...e.target.files]);e.target.value='';});$('replace-picker').addEventListener('change',e=>{const file=e.target.files&&e.target.files[0];const id=state.replaceTarget;state.replaceTarget=null;e.target.value='';if(file&&id)replaceFile(id,file);});const drop=$('dropzone');drop.addEventListener('dragover',e=>{e.preventDefault();if(!state.uploading)drop.classList.add('dragging');});drop.addEventListener('dragleave',()=>drop.classList.remove('dragging'));drop.addEventListener('drop',e=>{e.preventDefault();drop.classList.remove('dragging');addFiles([...e.dataTransfer.files]);});
  const debounces={};function changed(name){state[`${name}Page`]=1;if(name==='import')renderImport();else if(name==='task')loadTasks();else loadDocuments();}
  for(const name of ['task','import','doc'])$(`${name}-search`).addEventListener('input',()=>{clearTimeout(debounces[name]);state.tokens[name==='doc'?'doc':name==='task'?'tasks':name]=(state.tokens[name==='doc'?'doc':name==='task'?'tasks':name] || 0)+1;debounces[name]=setTimeout(()=>changed(name),250);});
  for(const [name,ids] of [['task',['task-filter','task-guide-filter','task-sort']],['import',['import-filter']],['doc',['doc-upload-filter','doc-qualification-filter','doc-completeness-filter','doc-status-filter','doc-reason-filter','doc-sort']]])for(const id of ids)$(id).addEventListener('change',()=>changed(name));
  for(const id of ['task-select'])$(id).addEventListener('change',e=>selectTask(e.target.value,false));
  document.addEventListener('change',e=>{if(e.target.id==='import-mode'){state.importMode=e.target.value;renderImport();return;}const revToggle=e.target.dataset.revToggle;if(revToggle!==undefined&&state.review){setRevision(Number(revToggle),e.target.checked?'accept':'reject');return;}const name=e.target.dataset.pagesize;if(name){state[`${name}Size`]=Number(e.target.value);changed(name);}});$('dev-user').addEventListener('input',identityChanged);$('task-name').addEventListener('input',()=>{state.createKey=null;if(!$('task-name-error').hidden)nameError(true);});$('detail-body').addEventListener('click',e=>{const quote=e.target.closest('.evidence.quote');if(quote&&!e.target.closest('a,button'))quote.classList.toggle('expanded');});$('close-detail').addEventListener('click',closeDetail);$('detail-overlay').addEventListener('click',e=>{if(e.target===$('detail-overlay'))closeDetail();});$('guide-file').addEventListener('change',e=>{const file=e.target.files?e.target.files[0]:null;$('guide-file-name').textContent=file?`已选择：${file.name}`:'尚未选择文件';$('guide-upload-btn').disabled=!file||state.guideUploading;});$('guide-overlay-close').addEventListener('click',closeGuidePanel);$('guide-overlay').addEventListener('click',e=>{if(e.target===$('guide-overlay'))closeGuidePanel();});$('help-close').addEventListener('click',closeHelp);$('help-overlay').addEventListener('click',e=>{if(e.target===$('help-overlay'))closeHelp();});document.addEventListener('keydown',e=>{if(!$('help-overlay').hidden&&e.key==='Escape'){closeHelp();}});document.addEventListener('keydown',e=>{if($('guide-overlay').hidden)return;if(e.key==='Escape'){closeGuidePanel();return;}if(e.key==='Tab'){const nodes=[...$('guide-overlay').querySelectorAll('button,summary,a[href],input,select')].filter(n=>!n.disabled&&n.offsetParent!==null),first=nodes[0],last=nodes.at(-1);if(!first)return;if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}});document.addEventListener('keydown',e=>{if(!state.review||$('detail-overlay').hidden||e.defaultPrevented||e.isComposing||e.ctrlKey||e.metaKey||e.altKey)return;const tag=(e.target&&e.target.tagName||'').toLowerCase();if((tag==='input'&&e.target.type!=='checkbox')||tag==='textarea'||tag==='select'||(e.target&&e.target.isContentEditable))return;const key=String(e.key||'').toLowerCase();if(key!=='a'&&key!=='r')return;const review=state.review;if(!review.revisions.length)return;const current=review.revisions.find(r=>String(r.del_id)===String(review.active))||review.revisions[0];e.preventDefault();setRevision(current.del_id,key==='a'?'accept':'reject');focusRevision(current.del_id);});document.addEventListener('keydown',e=>{if($('detail-overlay').hidden)return;if(e.key==='Escape'){closeDetail();return;}if(e.key==='Tab'){const nodes=[...$('detail-overlay').querySelectorAll('button,summary,a[href],input,select')].filter(n=>!n.disabled&&n.offsetParent!==null),first=nodes[0],last=nodes.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}});
  window.FundLexWorkbench={json,esc,toast,go,appPath,epoch:()=>state.epoch,view:()=>state.view,authenticated:()=>state.auth.mode!=='password'||!!state.auth.token};
  window.addEventListener('hashchange',()=>{if(location.hash.slice(1)!==state.view)go(location.hash.slice(1));});document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&document.title!==BASE_TITLE)document.title=BASE_TITLE;});try{$('dev-user').value=localStorage.getItem('fundlex-dev-user') || 'local-user';}catch{$('dev-user').value='local-user';}state.auth.token=storedToken();state.auth.user=storedUser();$('login-form').addEventListener('submit',submitLogin);$('register-form').addEventListener('submit',submitRegister);$('register-link').addEventListener('click',()=>switchAuthMode('register'));$('register-back').addEventListener('click',()=>switchAuthMode('login'));$('logout-btn').addEventListener('click',logout);$('password-btn').addEventListener('click',openPasswordDialog);$('pwd-cancel').addEventListener('click',closePasswordDialog);$('password-form').addEventListener('submit',submitPasswordChange);$('password-view').addEventListener('click',e=>{if(e.target===$('password-view'))closePasswordDialog();});document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('password-view').hidden)closePasswordDialog();});renderAuthUI();renderTask();renderImport();go(location.hash.slice(1));refresh(true).then(monitorTasks);setInterval(()=>{if(state.cap&&!state.refreshBusy&&document.visibilityState==='visible'&&(state.view==='overview'||(state.task&&['uploading','queued','running','paused'].includes(state.task.status)))){state.refreshBusy=true;refresh(true).finally(()=>{state.refreshBusy=false;});}},5000);setInterval(()=>{if(document.visibilityState==='visible')monitorTasks();},5000);document.addEventListener('keydown',e=>{if(e.key==='Escape'){$('notification-panel').hidden=true;$('notification-toggle').setAttribute('aria-expanded','false');}});document.addEventListener('click',e=>{if(!e.target.closest('.notification-center')){$('notification-panel').hidden=true;$('notification-toggle').setAttribute('aria-expanded','false');}});
})();
