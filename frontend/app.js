(() => {
  'use strict';
  const APP_BASE_PATH = document.querySelector('meta[name="fundlex-base-path"]')?.content || (location.pathname === '/test' || location.pathname.startsWith('/test/') ? '/test' : '');
  const appPath = path => `${APP_BASE_PATH}${path}`;
  const fetch = (path, options) => window.fetch(typeof path === 'string' && path.startsWith('/api/') ? appPath(path) : path, options);
  const $ = id => document.getElementById(id), MiB = 1024 * 1024;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const size = n => n >= MiB ? `${(n / MiB).toFixed(1)} MiB` : `${Math.ceil(n / 1024)} KiB`;
  const labels = {...(window.FUNDLEX_STATUS_LABELS||{}),uploading:'上传中',queued:'排队中',running:'处理中',leased:'处理中',retry_wait:'等待重试',paused:'已暂停',completed:'处理完成',completed_with_exceptions:'处理完成（部分需人工核对）',succeeded:'已处理',failed:'处理失败',eligible:'可以处理',excluded_by_fund_type:'不适用',pending:'未判定',complete:'文件已完整交付',incomplete:'处理完成',not_generated:'未生成',accepted:'已上传',rejected:'接收失败',not_started:'尚未接收',partial:'部分上传',sealed_incomplete:'上传未完成',applied:'已修改',satisfied:'已符合',satisfied_no_change:'已符合',not_applicable:'不适用',not_matched:'未命中',needs_edit:'待修改',planned:'已规划',unresolved:'未自动修改',excluded:'已排除',unknown:'未确认',evaluation_modified:'已修改（评测）',evaluation_unmodified:'无需修改（评测）',evaluation_modified_with_exceptions:'已修改（部分需核对，评测）',diagnosed:'仅出报告未修改',complete:'文件已完整交付',complete_with_exceptions:'已交付（部分需人工核对）',uploaded:'待解析',parsing:'解析中',parsed:'已解析',validated:'校验通过',parse_failed:'解析失败',released:'已发布',archived:'已归档'};
  const reasons = {
    FUND_TYPE_EVIDENCE_AMBIGUOUS:'基金类型证据不明确，已保守停止该合同', FUND_TYPE_UNKNOWN:'无法确定基金类型，已保守停止该合同', EXISTING_REVISION_UNSUPPORTED:'合同带有未处理的修订痕迹，请先在 Word 中接受/拒绝全部修订并另存后重试',
    DOCUMENT_IDENTITY_EVIDENCE_MISSING:'缺少可核验的基金合同身份依据，已停止处理', NON_CONTRACT_DOCUMENT:'文档未被确认为基金合同，已停止处理', DOCUMENT_TYPE_CONFLICT:'文档类型依据互相冲突，已停止处理',
    FUND_TYPE_EVIDENCE_MISSING:'缺少明确的基金类型依据，已停止处理', FUND_TYPE_EVIDENCE_INVALID:'基金类型引用未通过原文核验，已停止处理', FUND_TYPE_INVESTMENT_EVIDENCE_MISSING:'缺少可核验的投资范围依据，已停止处理', FUND_TYPE_INVESTMENT_EVIDENCE_CONFLICT:'基金类型与投资范围依据冲突，已停止处理', FUND_TYPE_OPERATION_EVIDENCE_INVALID:'运作方式依据未通过核验，已停止处理', FUND_TYPE_CD_MANDATE_EVIDENCE_MISSING:'缺少同业存单投资约定依据，已停止处理', QUALIFICATION_CONTEXT_LIMIT:'资格判断所需文本超出支持范围，已停止处理',
    MODEL_TYPE_CONFLICT:'模型判断与合同类型依据不一致，已停止处理', MODEL_EVIDENCE_INVALID:'模型引用未通过合同原文核验', MODEL_QUOTE_MISMATCH:'处理结果引用与合同原文不一致', MODEL_CONFIG_MISSING:'模型处理服务尚未配置', MODEL_HTTP_ERROR:'模型服务返回异常，未生成可用结果', MODEL_CONTEXT_LIMIT:'处理文本超出支持范围', MODEL_RESPONSE_LIMIT:'处理结果超过接收限制', MODEL_CHECKPOINT_UNAVAILABLE:'处理检查点暂不可用，任务已暂停保护',
    PROFILE_CLASS_SET_CONFLICT:'份额类别依据互相冲突，相关动作未执行', PROFILE_CLASS_NAME_EVIDENCE_MISSING:'缺少份额类别名称依据，相关动作未执行', PROFILE_EVIDENCE_INVALID:'份额或收费引用未通过原文核验', PROFILE_FEE_POLARITY_UNVERIFIED:'无法确认相关费用是否收取，相关动作未执行', PROFILE_MANAGEMENT_FEE_CONFLICT:'管理费依据互相冲突，相关动作未执行', RULE_CONDITION_UNKNOWN:'无法确认规则适用条件，未自动修改',
    DOCUMENT_PROTECTED:'合同设置了编辑保护，无法安全处理', SIGNED_OR_MACRO_UNSUPPORTED:'合同包含签名或宏结构，无法安全处理', STRICT_OOXML_UNSUPPORTED:'该 DOCX 格式版本暂不支持安全处理', ZIP_INVALID:'DOCX 文件包损坏或格式异常', XML_INVALID:'DOCX 内部内容格式异常', INPUT_INTEGRITY_FAILED:'源文件完整性校验失败，已停止处理', ENGINE_SCHEMA_MISMATCH:'处理引擎版本已变化，请按当前版本新建任务', RULESET_HASH_MISMATCH:'修改规则已更新，请新建任务', MISSING_VERIFIED_ARTIFACTS:'修改后的合同未通过完整性校验，暂不开放下载', ARTIFACT_VERIFICATION_MISMATCH:'修改后的合同校验未通过，暂不开放下载', OUTPUT_IO_ERROR:'处理文件写入失败，未生成可用结果', PROCESSING_FAILED:'合同处理发生异常，已隔离该合同',
    MODEL_SCHEMA_INVALID:'处理结果格式未通过校验', MODEL_EVIDENCE_UNKNOWN:'处理结果引用的证据无法核验', PROFILE_EVIDENCE_INCOMPLETE:'份额与收费证据不完整',
    ACTION_RELEASE_GATE_CLOSED:'该类修改暂未开放自动执行', RELEASE_GATE_CLOSED:'该类修改暂未开放自动执行', TARGET_SCOPE_UNRESOLVED:'无法确定条款适用范围，未自动修改', UNSUPPORTED_TARGET_STRUCTURE:'条款结构暂不支持安全修改', LOCAL_TARGET_VERIFICATION_REQUIRED:'条款位置需要进一步校验，未自动修改',
    V2_ALREADY_SATISFIED:'原合同已符合要求，无需修改', V2_TARGET_NOT_LOCATED:'未能在合同中准确定位该条款，保持原文', V2_TARGET_AMBIGUOUS:'条款位置不唯一，按安全规则保持原文', V2_CLASS_DEFINITION_CONFLICT:'份额类别与收费信息不一致，保持原文', V2_HYBRID_CLASS_FEE_UNSUPPORTED:'存在同时收两种费用的类别，无法安全套用统一规则', V2_EXISTING_CLAUSE_UNSUPPORTED:'该段已包含部分直销条款，为避免重复保持原文',
    V2_SLOT_UNRESOLVED:'类别收费分组证据不足，规则文案无法按实际类别生成，保持原文', V2_SCOPE_TEXT_MISMATCH:'整句或整段与规则指引旧文不一致，为避免丢字保持原文', V2_DELIVERY_REQUIRES_RELEASED_PACKAGE:'修改规则尚未发布，暂不写入合同', V2_RELEASE_CONTEXT_UNVERIFIED:'引擎或模型配置与上线资料不一致，已停止写入，请重新发布', V2_RELEASE_NOT_SEPARATE:'修改规则尚未发布，暂不启用自动修改', V2_RELEASE_EVIDENCE_MISSING:'修改规则上线资料不完整，暂不启用自动修改', V2_RELEASE_METRIC_BELOW_THRESHOLD:'修改规则尚未达到上线标准，暂不启用自动修改',
    V2_FACT_ROLE_MISMATCH:'改写依据无法对应到合同原文，按安全规则保持原文', V2_FACT_INCOMPLETE:'改写依据不完整，保持原文', V2_FACT_ROLE_INVALID:'改写依据来源无效，保持原文', V2_VERIFY_NOT_SATISFIED:'独立复核认为改写未完全满足要求，保持原文', V2_VERIFY_QUOTE_MISMATCH:'独立复核引用无法核对，保持原文', V2_CONTENT_CHECK_FAILED:'改写内容未通过规则校验，保持原文', V2_REPLACEMENT_INVALID:'改写内容格式不符合要求，保持原文', V2_REPLACEMENT_UNCHANGED:'改写内容与原文相同，无需修改', V2_SOURCE_QUOTE_MISMATCH:'模型定位与系统记录不一致，保持原文', V2_JOIN_UNSAFE:'改写内容与原文衔接未通过校验，保持原文', V2_ACTION_PARTIAL_REVERTED:'同一动作存在未完成目标，整组保持原文', V2_BODY_SUMMARY_CONFLICT:'正文与摘要改写不一致，整组保持原文', V2_LOCATE_SCOPE_TOO_WIDE:'候选条款范围过宽，按安全规则保持原文', CROSS_PARAGRAPH_TARGET_UNSUPPORTED:'目标内容跨段落，暂不支持安全修改', SHORT_HOLDING_NON_TARGET_HOST:'该句属于费用归属条款，由另一项规则处理',
    MODEL_NETWORK_ERROR:'模型服务连接暂时失败', MODEL_RETRY_EXHAUSTED:'模型服务重试后仍未成功', MODEL_CIRCUIT_OPEN:'模型服务连续异常，任务已暂停保护', MODEL_GLOBAL_CALL_BUDGET_EXCEEDED:'任务处理遇到模型调用限制，请稍后重试；若持续出现请联系支持', MODEL_CALL_BUDGET_EXCEEDED:'任务处理遇到模型调用限制，请稍后重试；若持续出现请联系支持', MODEL_COST_BUDGET_EXCEEDED:'任务处理遇到模型调用限制，请稍后重试；若持续出现请联系支持', MODEL_LEDGER_UNAVAILABLE:'任务处理遇到模型调用限制，请稍后重试；若持续出现请联系支持', MODEL_NOT_CONFIGURED:'处理服务尚未配置', WORKER_ATTEMPTS_EXHAUSTED:'处理重试次数已达上限', TEMPORARY_STORAGE_FAILURE:'文件存储暂时异常',
    INVALID_DOCX:'文件不是有效的可编辑 DOCX', DOCX_INVALID:'文件不是有效的可编辑 DOCX', UPLOAD_TOO_LARGE:'文件超过接收大小限制', UNSUPPORTED_FORMAT:'文件格式不受支持，仅接收 DOCX', DOCUMENT_VALIDATION_FAILED:'DOCX 内容校验未通过', UPLOAD_REJECTED:'文件接收校验未通过', UNSUPPORTED_FILE_FORMAT:'仅接收可编辑 DOCX 文件', LEGACY_DOC_UNSUPPORTED:'检测到 Word 97-2003 格式（.doc），请用 Word/WPS 另存为 .docx 后重新上传', LEGACY_DOC_CONVERT_UNAVAILABLE:'服务器暂不支持 .doc 自动转换，请另存为 .docx 后重新上传', LEGACY_DOC_CONVERT_FAILED:'.doc 自动转换失败，请另存为 .docx 后重新上传', LEGACY_DOC_CONVERT_TIMEOUT:'.doc 自动转换超时，请另存为 .docx 后重新上传', LEGACY_DOC_CONVERT_TOO_LARGE:'.doc 文件过大无法自动转换，请另存为 .docx 后重新上传', UPLOAD_SIZE_LIMIT:'文件超过接收大小限制', DUPLICATE_DOCX_MEMBER:'DOCX 内部存在重复文件条目，无法安全接收', DOCX_PART_SIZE_LIMIT:'DOCX 内部内容超过大小限制', DOCX_COMPRESSION_RATIO_LIMIT:'DOCX 压缩结构超出安全接收限制', DOCX_EXPANDED_SIZE_LIMIT:'DOCX 解压内容超过安全接收限制', UPLOAD_REQUEST_SIZE_LIMIT:'本次文件接收超出限制，请重新补传', MANIFEST_ENTRY_NOT_FOUND:'文件未包含在原任务清单中', MANIFEST_FILE_MISMATCH:'本地文件与原任务清单不匹配，请重新选择', UPLOAD_IDENTITY_CONFLICT:'文件身份发生冲突，请确认源文件后重试', LAST_ADMIN_REQUIRED:'不能停用最后一个可用管理员，请先创建或启用其他管理员',
    DOCX_VALIDATION_FAILED:'DOCX 文件内容或结构校验未通过', INVALID_DOCX_PACKAGE:'文件不是有效的可编辑 DOCX', ENCRYPTED_DOCX:'文件已加密，无法安全处理', DOCX_SIZE_LIMIT_EXCEEDED:'文件超过接收大小限制', DOCX_UNSUPPORTED:'DOCX 结构不受支持', DOCX_SECURITY_LIMIT:'DOCX 解压校验超出安全限制',
    GUIDE_NOT_READY:'当前指引不可用或尚未解析完成，请先在「我的指引」启用可用指引', GUIDE_NOT_ENABLEABLE:'该指引尚未解析完成，暂不能启用', GUIDE_NOT_PARSEABLE:'当前状态不能重新解析', GUIDE_PARSE_FAILED:'指引解析未完成，可查看问题后重新解析', GUIDE_DOCUMENT_INVALID:'指引文档未通过解析校验', GUIDE_RULE_INVALID:'规则编号无效，请刷新后重试', GUIDE_RULES_ALL_DISABLED:'至少保留一条启用规则', MODEL_SETTINGS_LOCKED:'模型配置由部署文件管理，请在服务器环境修改', MODEL_API_KEY_ENV_REQUIRED:'请填写 API Key 环境变量名', MODEL_REVIEW_KEY_REQUIRED:'复核模型使用不同地址时必须提供独立密钥变量', ENGINE_OR_RULESET_REQUIRED:'提交缺少引擎或规则信息，请刷新后重试', ENGINE_CONFLICT:'引擎与规则信息冲突，请刷新后重试', ENGINE_UNSUPPORTED:'当前环境不支持所选引擎', BUILTIN_SOURCE_UNAVAILABLE:'内置指引不提供原件下载',BUILTIN_SOURCE_DOCX_MISSING:'内置默认指引的原文档案在服务端缺失，请稍后重试；若多次出现请联系管理员。',GUIDE_TEXT_DIFF_UNREADABLE:'两版指引原文暂时无法比对（版本解析异常），请换两个版本再试；反复出现请联系管理员'
  };
  const reason = code => reasons[code] || (code ? '处理未安全完成，请稍后重试或联系管理员' : '');
  const badge = (value, override) => `<span class="badge b-${['eligible','succeeded','completed','complete','accepted','satisfied','satisfied_no_change','evaluation_modified','evaluation_unmodified','parsed','released','validated','incomplete'].includes(value)?'green':['failed','completed_with_exceptions','rejected','parse_failed'].includes(value)?'red':['running','queued','leased','uploading','parsing'].includes(value)?'blue':['paused','excluded_by_fund_type','retry_wait'].includes(value)?'amber':'gray'}">${esc(override || labels[value] || '未确认')}</span>`;
  // FL-D1056（用户原话「指引生成的功能先在前端隐藏，不要暴露出来了」）：只藏不删——
  // 侧池/启动器/直达路由全部视一览，但 API/helper/页面文件保留。
  // 恢复路径：把本常量换回 true 即一键恢复全部指引生成入口。
  const SHOW_FUNDLEX_GUIDE_GENERATION = false;
  window.__SHOW_FUNDLEX_GUIDE_GENERATION__ = SHOW_FUNDLEX_GUIDE_GENERATION;

  const state = {view:'overview',epoch:0,controllers:new Set(),tokens:{},tasks:[],selected:null,task:null,cap:null,tasksLoaded:false,guideDismissed:(()=>{try{return localStorage.getItem(`fundlex-guide-dismissed:${localStorage.getItem('fundlex-dev-user')||'user'}`)==='1';}catch{return false;}})(),imports:[],recover:null,uploading:false,uploadToken:null,createKey:null,taskPage:1,importPage:1,docPage:1,taskSize:20,importSize:20,docSize:20,taskDocs:[],detail:null,focusReturn:null,guides:null,guidesFailed:false,guideBusy:null,guideUploading:false,guideTimer:null,guideDetail:null,auth:{mode:'dev',loginRequired:false,registrationOpen:false,token:'',user:null},review:null,reviewDocs:null,reviewDocsTask:null,reviewDocsKey:'',reviewDecisions:new Map(),uploadProgress:null,replaceTarget:null,toastSeq:0,importSession:0,refreshBusy:false,overviewStats:null,taskGuides:null,modelData:null,modelEdit:null,modelVerified:{},modelCopyFrom:null};
  const notifications=[];let taskStatuses=new Map(),notificationBusy=false,feishuOAuthTimer=null,feishuOAuthEpoch=0,feishuExpiresAt=0,feishuBound=false;
  function renderNotifications(){const unread=notifications.filter(n=>!n.read).length;$('notification-count').textContent=unread||'';$('notification-count').hidden=!unread;$('notification-toggle').setAttribute('aria-label',unread?`消息，${unread} 条未读`:'消息');$('notification-list').innerHTML=notifications.length?notifications.map(n=>`<li><p>${esc(n.message)}</p>${n.taskId?`<button class="btn-link" data-task="${esc(n.taskId)}">查看任务</button>`:''}<time>${esc(new Date(n.time).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'}))}</time></li>`).join(''):'<li>暂无重要消息</li>';}
  function notify(message,error=false,taskId=null){if(!message)return;const recent=notifications.find(n=>n.message===message&&n.taskId===taskId&&Date.now()-n.time<60000);if(recent)return;notifications.unshift({message,error,taskId,time:Date.now(),read:false});notifications.splice(50);renderNotifications();}
  // 错误同时进入铃铛与全局提示；成功类操作只做全局轻提示。
  function notice(message,error=false){if(error)toast(message,true);}
  let BASE_TITLE='FundLex合同修订工作台';
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
  async function monitorTasks(){if(notificationBusy||!state.cap||(state.auth.mode==='password'&&!state.auth.token))return;notificationBusy=true;const epoch=state.epoch;try{const p=await json('/api/tasks?page=1&page_size=50');if(!identityCurrent(epoch))return;const next=new Map();for(const t of p.items){next.set(t.id,t.status);const old=taskStatuses.get(t.id);if(old&&old!==t.status&&['completed','completed_with_exceptions','failed','paused'].includes(t.status))notify(`${t.name}：${t.status==='failed'?'处理失败':t.status==='completed_with_exceptions'?'处理结束（含异常）':t.status==='completed'?'处理结束，可查看结果':'任务已暂停，请查看原因'}`,t.status==='paused',t.id);}taskStatuses=next;}catch(e){if(identityCurrent(epoch))errorNotice(e);}finally{notificationBusy=false;}}
  function owner() { return $('dev-user').value.trim(); }
  const identityCurrent = epoch => epoch===state.epoch;
  const AUTH_TOKEN_KEY='fundlex-auth-token',AUTH_USER_KEY='fundlex-auth-user';
  function storedToken(){try{return sessionStorage.getItem(AUTH_TOKEN_KEY) || '';}catch{return '';}}
  function storedUser(){try{const raw=sessionStorage.getItem(AUTH_USER_KEY);return raw?JSON.parse(raw):null;}catch{return null;}}
  function setAuthSession(token,user){state.auth.token=token || '';state.auth.user=user || null;try{if(token)sessionStorage.setItem(AUTH_TOKEN_KEY,token);else sessionStorage.removeItem(AUTH_TOKEN_KEY);if(user)sessionStorage.setItem(AUTH_USER_KEY,JSON.stringify(user));else sessionStorage.removeItem(AUTH_USER_KEY);}catch{}renderAuthUI();}
  function clearAuthSession(){setAuthSession('',null);}
  function renderAuthUI(){const box=$('topbar-user');if(!box)return;const user=state.auth.user;const active=state.auth.mode==='password'&&!!user;box.hidden=!active;if(active)$('topbar-username').textContent=user.display_name||user.username||'已登录';const settingsUser=$('settings-current-user');if(settingsUser)settingsUser.textContent=user?(user.display_name||user.username||'已登录'):(state.auth.mode==='dev'?(`本地开发身份 ${owner()}`):'—');const settingsPwdBtn=document.querySelector('[data-action="open-password"]');if(settingsPwdBtn){const canChange=state.auth.mode==='password'&&!!user;settingsPwdBtn.disabled=!canChange;settingsPwdBtn.title=canChange?'':'本地开发身份无需密码';}updateSettingsNav();updateUsersNav();updateGuideNav();}
  function updateSettingsNav(){const btn=document.querySelector('.sidebar [data-nav="settings"]');if(btn)btn.hidden=false;}
  function updateUsersNav(){const btn=$('nav-users');if(!btn)return;const show=state.auth.mode==='password'&&!!state.auth.user&&state.auth.user.role==='admin';btn.hidden=!show;if(!show&&state.view==='users')go('overview');}
  function updateGuideNav(){const btn=document.querySelector('.sidebar [data-nav="guide"]');if(!btn)return;const show=state.auth.mode!=='password'||!!state.auth.user;btn.hidden=!show;if(!show&&state.view==='guide')go('overview');}
  function showLogin(message,kind='error'){const view=$('login-view');if(!view)return;const wasHidden=view.hidden;view.hidden=false;const app=document.querySelector('.app');if(app)app.inert=true;const hint=$('register-hint');if(hint)hint.hidden=!(state.auth.mode==='password'&&state.auth.registrationOpen);const box=$('login-error');box.textContent=message || '';box.hidden=!message;box.classList.toggle('field-note',kind==='info');if(wasHidden){switchAuthMode('login');box.hidden=!message;(($('login-username').value)?$('login-password'):$('login-username')).focus();}}
  function switchAuthMode(mode){const login=$('login-form'),register=$('register-form');if(!login||!register)return;const showRegister=mode==='register';login.hidden=showRegister;register.hidden=!showRegister;if(showRegister){$('register-error').hidden=true;$('register-username').focus();}else{$('login-error').hidden=true;$('login-username').focus();}}
  function hideLogin(){const view=$('login-view');if(!view||view.hidden)return;view.hidden=true;$('login-password').value='';const app=document.querySelector('.app');if(app)app.inert=false;}
  function ticket(scope) { const token=(state.tokens[scope] || 0)+1; state.tokens[scope]=token; return {epoch:state.epoch,token,scope}; }
  function current(t) { return identityCurrent(t.epoch) && state.tokens[t.scope]===t.token; }
  function stale() { return new DOMException('请求已被新的操作替代','AbortError'); }
  async function api(path,options={}) {
    const epoch=state.epoch,identity=owner(),token=state.auth.token; if(!identity&&!token&&state.auth.mode!=='password'&&path!=='/api/capabilities')throw new Error('请在开发设置中填写本地开发身份。');
    if(!path.startsWith('/api/') || path.startsWith('//'))throw new Error('服务端返回了不支持的下载路径。');
    const controller=new AbortController();state.controllers.add(controller);const headers=new Headers(options.headers || {}); if(token)headers.set('Authorization',`Bearer ${token}`); if(identity)headers.set('X-FundLex-User',identity);
    try { let response;try{response=await fetch(path,{...options,headers,signal:controller.signal,cache:'no-store'});}catch(error){if(!identityCurrent(epoch))throw stale();if(error&&error.name==='AbortError')throw error;const offline=new Error('无法连接本地服务，请确认服务已启动，然后重试。');offline.code='CONNECTION';throw offline;} if(!identityCurrent(epoch))throw stale();
      if(response.status===401&&state.auth.mode==='password'){handleSessionExpired();const expired=new Error('登录状态已失效，请重新登录。');expired.code=401;throw expired;}
      if(!response.ok) { let detail=''; try { const p=await response.json();detail=typeof p.detail==='string'?p.detail:JSON.stringify(p.detail || p); } catch { detail=response.statusText; }
        if(!identityCurrent(epoch))throw stale(); const messages={401:'开发身份无效，请检查开发设置。',403:'没有访问此结果的权限。',404:'该任务或结果不存在，或当前身份无权访问。',503:'服务暂不可用；生产身份服务尚未配置时将关闭访问。',413:'文件超过接收限制，请检查文件大小。',409:'任务状态已变化或请求存在冲突，请稍后重试。'};
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
  function humanErrorText(error,fallback='处理未完成，请稍后重试；反复出现请联系管理员。'){
    const message=String(error&&error.message||'').trim();
    if(!message)return fallback;
    if(error&&(error.code!=null||error.raw))return message;  // 已过 api() 人话层或含后端明文详情的消息，放行
    if(/^(TypeError|SyntaxError|ReferenceError|RangeError)$/i.test(error.name||''))return fallback;
    if(/^(TypeError|SyntaxError|Failed to fetch|NetworkError|Load failed|fetch failed)\b/i.test(message))return fallback;
    if(/Unexpected token|is not a function|is not defined|Cannot read properties|undefined is not|null is not/i.test(message))return fallback;
    return message;
  }
  function errorNotice(error,prefix=''){if(error.name!=='AbortError')toast(prefix+humanErrorText(error),true);}
  function param(values) { const p=new URLSearchParams();for(const [k,v] of Object.entries(values))if(v!==''&&v!=null)p.set(k,v);return p.toString(); }
  function pathTask(id=state.selected) { return `/api/tasks/${encodeURIComponent(id)}`; }
  function pathDoc(doc) { return `/api/batches/${encodeURIComponent(doc.batch_id)}/documents/${encodeURIComponent(doc.document_id)}`; }
  function emptyRow(cols,message) {return `<tr><td colspan="${cols}"><div class="empty"><strong>${esc(message)}</strong></div></td></tr>`;}
  // Keep live controls and unchanged rows mounted while polling updates data.
  function patchHTML(element,html){
    if(!element)return;
    // FL-D1015：Slim Select 把自身 data 当权威——必须在 SS 观察器交付之前（同一宏任务内）
    // 喂新数据，否则 SS 会先把原生 select 夹回旧数据（实测夹空）；queueMicrotask 先于观察器。
    queueMicrotask(()=>window.FundLexSelectKit?.feed(element));
    const template=document.createElement('template');template.innerHTML=html;
    if(element.innerHTML===template.innerHTML)return;
    const compatible=(a,b)=>a&&a.nodeType===b.nodeType&&(a.nodeType!==1||a.tagName===b.tagName);
    function sync(parent,fresh){
      const keyed=new Map([...parent.children].filter(n=>n.dataset.rowKey).map(n=>[n.dataset.rowKey,n]));
      let cursor=parent.firstChild;
      for(const incoming of [...fresh.childNodes]){
        const key=incoming.nodeType===1?incoming.dataset.rowKey:null;
        let node=key?keyed.get(key):cursor;
        if(!compatible(node,incoming)||(!key&&node?.nodeType===1&&node.dataset.rowKey))node=null;
        if(!node){node=incoming.cloneNode(true);parent.insertBefore(node,cursor);}
        else{
          if(node!==cursor)parent.insertBefore(node,cursor);
          if(node.nodeType===1){
            for(const attr of [...node.attributes])if(!incoming.hasAttribute(attr.name))node.removeAttribute(attr.name);
            for(const attr of incoming.attributes)if(node.getAttribute(attr.name)!==attr.value)node.setAttribute(attr.name,attr.value);
            sync(node,incoming);
          }else if(node.nodeValue!==incoming.nodeValue)node.nodeValue=incoming.nodeValue;
        }
        cursor=node.nextSibling;
      }
      while(cursor){const next=cursor.nextSibling;cursor.remove();cursor=next;}
    }
    sync(element,template.content);
  }
  function refreshNote(scope,failed=false){
    let note=$(scope+'-refresh-note');
    if(!note&&failed){note=document.createElement('p');note.id=scope+'-refresh-note';note.className='refresh-note';note.setAttribute('role','status');$(scope+'-pagination').after(note);}
    if(note){note.hidden=!failed;if(failed)note.textContent='刷新暂未成功，当前保留上次结果；请稍后重试。';}
  }
  function pagination(name,total,page,pageSize) {const pages=Math.max(1,Math.ceil(total/pageSize));return `<span>共 ${total} 条 · 第 ${page} / ${pages} 页</span><div class="controls"><label for="${name}-page-size">每页</label><select id="${name}-page-size" data-pagesize="${name}">${[20,50,100].map(n=>`<option value="${n}" ${n===pageSize?'selected':''}>${n}</option>`).join('')}</select><button class="btn btn-sm" data-page="${name}" data-dir="prev" ${page<=1?'disabled':''}>上一页</button><button class="btn btn-sm" data-page="${name}" data-dir="next" ${page>=pages?'disabled':''}>下一页</button></div>`;}
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
    box.hidden=false;patchHTML(box,chips.join('')+`<button type="button" class="clear-filters" data-clear-filters="${scope}">清除全部</button>`);
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
  const VIEW_TITLES={workspace:'工作台',overview:'合同修改',import:'新建合同修改',task:'修改任务详情',document:'合同结果与修订审阅',guide:'我的指引',models:'模型配置',settings:'设置',feishu:'飞书绑定',users:'用户管理',compare:'合同比对',generation:'指引生成'};
  function renderFooter(){const el=$('app-version');if(el)el.textContent=state.cap?.app_version?`v${state.cap.app_version}`:'—';}
  // Identity reset uses the same location renderer; there is no second title.
  function renderTopbarTitle(view){renderBreadcrumb(view);}
  function businessListKey(view){return `fundlex-v1-list-route:${state.auth.user?.id||owner()}:${view}`;}
  function saveBusinessList(){
    if(!['compare','generation'].includes(state.view)||state.route?.mode!=='list')return;
    const route={mode:'list'};for(const key of ['q','status','page'])if(state.route[key]!=null)route[key]=String(state.route[key]);
    try{sessionStorage.setItem(businessListKey(state.view),JSON.stringify(route));}catch{}
  }
  function businessListRoute(view){
    try{const saved=JSON.parse(sessionStorage.getItem(businessListKey(view))||'{}'),route={mode:'list'};for(const key of ['q','status','page'])if(typeof saved[key]==='string')route[key]=saved[key];return route;}catch{return {mode:'list'};}
  }
  function renderBreadcrumb(view=state.view){
    const el=$('breadcrumb');if(!el)return;
    const items=[],add=(label,nav=null,id=null)=>items.push({label,nav,id});
    const task=state.task?.id===state.route?.id?state.task:null;
    if(view==='import'){add('合同修改','overview');add(state.recover?'补传文件':'新建任务');}
    else if(view==='task'){add('合同修改','overview');add('任务详情');}
    else if(view==='document'){add('合同修改','overview');add(task?.name||'所属任务','task',state.route?.id);add(state.route?.tab==='review'?'合同审阅':'合同结果');}
    else if(view==='compare'||view==='generation'){const mode=state.route?.mode||'list';add(VIEW_TITLES[view],mode==='list'?null:view);if(mode!=='list')add(mode==='new'?'新建任务':'任务详情');}
    else add(VIEW_TITLES[view]||'工作台');
    const objectPage=['task','document'].includes(view)||(['compare','generation'].includes(view)&&state.route?.mode==='detail');
    const markup=items.map((item,index)=>{
      const current=index===items.length-1,separator=index?'<span class="crumb-sep" aria-hidden="true">›</span>':'';
      if(current)return separator+(objectPage?`<span class="crumb-current" aria-current="page">${esc(item.label)}</span>`:`<h1 class="crumb-current" aria-current="page">${esc(item.label)}</h1>`);
      return separator+`<button type="button" class="crumb-link" data-crumb="${esc(item.nav)}" ${item.id?`data-crumb-id="${esc(item.id)}"`:''} title="${esc(item.label)}">${esc(item.label)}</button>`;
    }).join('');
    if(el.innerHTML!==markup)el.innerHTML=markup;
    const objectName=view==='document'?state.detail?.name:view==='task'?task?.name:state.objectTitle;
    state.pageTitle=`${objectPage&&objectName?objectName+' · ':''}${items.map(item=>item.label).join(' › ')} · FundLex`;
    BASE_TITLE=state.pageTitle;document.title=BASE_TITLE;
  }
  function setObjectTitle(view,title){if(state.view===view){state.objectTitle=String(title||'');renderBreadcrumb();}}
  function openHelp(){const view=$('help-overlay');if(!view)return;state.focusReturn=document.activeElement;view.hidden=false;document.querySelector('.app').inert=true;$('help-close').focus();}
  function closeHelp(){const view=$('help-overlay');if(!view||view.hidden)return;view.hidden=true;if($('login-view').hidden&&$('password-view').hidden)document.querySelector('.app').inert=false;if(state.focusReturn){state.focusReturn.focus();state.focusReturn=null;}}
  function routeFromHash(){const raw=location.hash.slice(1),cut=raw.indexOf('?'),view=(cut<0?raw:raw.slice(0,cut))||'workspace';return {view,...Object.fromEntries(new URLSearchParams(cut<0?'':raw.slice(cut+1)))};}
  function routeHash(route){const {view,...values}=route;const query=param(values);return `#${view}${query?'?'+query:''}`;}
  function dispatchRoute(){document.dispatchEvent(new CustomEvent('fundlex:route',{detail:{...state.route}}));}
  // FL-D1056：指引生成只藏不删——入口锚点隐藏（侧池/启动器下单等隐；API/page 全栈照常）。
  function hideGuideGenerationEntrypoints(){
    if(SHOW_FUNDLEX_GUIDE_GENERATION)return;
    document.querySelectorAll('[data-nav="generation"]').forEach(el=>{el.setAttribute('hidden','');el.setAttribute('aria-hidden','true');});
    const launcher=document.querySelector('[data-workspace-new="generation"]')?.closest('.workspace-launcher');
    if(launcher)launcher.setAttribute('hidden','');
  }
  if(!SHOW_FUNDLEX_GUIDE_GENERATION){
    hideGuideGenerationEntrypoints();
    document.addEventListener('fundlex:route',hideGuideGenerationEntrypoints);
  }
  function go(view,options={}) {
    if(view.includes('?')){const query=view.slice(view.indexOf('?')+1);view=view.split('?')[0];options={...Object.fromEntries(new URLSearchParams(query)),...options};}
    // FL-D1056：指引生成只藏不删——直达 #/generation 一律回落工作台，咱不生怒不揭功能页。
    if(!SHOW_FUNDLEX_GUIDE_GENERATION&&view==='generation'){view='workspace';options={};}
    if(!view.endsWith('models')){state.modelEdit=null;state.modelCopyFrom=null;}
    if(view==='revision')view='overview';
    if(!Object.hasOwn(VIEW_TITLES,view)){if(view&&view!=='workspace')toast('链接无效或已过期，已回到工作台。','info');view='workspace';}
    if(view==='users'&&!(state.auth.mode==='password'&&state.auth.user?.role==='admin'))view='workspace';
    if(['compare','generation'].includes(view)&&!Object.keys(options).length)options=businessListRoute(view);
    const next={view,...options};if(['compare','generation'].includes(view)&&!next.mode)next.mode='list';
    if(['task','document'].includes(view)&&!next.id)next.id=view==='task'&&state.view==='document'?state.route?.id:state.selected;
    const changed=state.route&&routeHash(state.route)!==routeHash(next);
    if(changed&&((state.view==='generation'&&window.FundLexGuideGeneration?.hasUnsavedChanges?.())||(state.view==='compare'&&window.FundLexCompare?.hasUnsavedChanges?.()))&&!confirm('当前有未保存的更改，确认离开此页？')){history.replaceState(null,'',routeHash(state.route));return;}
    if(state.view==='overview')saveRevisionFilters();
    saveBusinessList();
    if(state.view==='document'&&view!=='document')closeDetail();
    const prior=state.route;if(!prior||prior.view!==view||prior.id!==next.id||prior.mode!==next.mode)state.objectTitle='';state.view=view;state.route=next;const hash=routeHash(next);state.routeHash=hash;
    if(location.hash!==hash)location.hash=hash;
    document.querySelectorAll('.section').forEach(n=>n.classList.toggle('active',n.id===`view-${view}`));
    const parent=['import','task','document'].includes(view)?'overview':view;
    document.querySelectorAll('[data-nav].nav-btn').forEach(n=>{const active=n.dataset.nav===parent;n.classList.toggle('active',active);if(active)n.setAttribute('aria-current','page');else n.removeAttribute('aria-current');});
    renderBreadcrumb(view);if(!prior||prior.view!==view||prior.mode!==next.mode||prior.id!==next.id||prior.document!==next.document)document.querySelector('.main').scrollTop=0;
    document.dispatchEvent(new CustomEvent('fundlex:view',{detail:view}));dispatchRoute();
    if(!state.cap)return;
    if(view==='users')loadUsers();if(view==='guide')loadGuides();if(view==='feishu'){loadFeishuBinding();loadFeishuApp();}if(view==='models')loadModelSettings();
    if(view==='overview'){restoreRevisionFilters();loadTasks();if(!state.taskGuides)loadTaskGuides(true);}
    if(view==='task'){if(!state.taskGuides)loadTaskGuides(true);if(next.id&&state.selected!==next.id)selectTask(next.id,false);else loadDocuments();}
    if(view==='document')openDocumentRoute(next);
  }
  function revisionFilterKey(){return `fundlex-v1-revision-list:${state.auth.user?.id||owner()}`;}
  function saveRevisionFilters(){try{sessionStorage.setItem(revisionFilterKey(),JSON.stringify({page:state.taskPage,values:Object.fromEntries(['task-search','task-filter','task-guide-filter','task-sort'].map(id=>[id,$(id).value]))}));}catch{}}
  function restoreRevisionFilters(){try{const value=JSON.parse(sessionStorage.getItem(revisionFilterKey())||'null');if(value){state.taskPage=Number(value.page)||1;for(const [id,v] of Object.entries(value.values||{}))if($(id))$(id).value=v;}}catch{}}
  async function openDocumentRoute(route){
    const t=ticket('document-route');
    if(!route.id||!route.document){$('document-host').querySelector('#detail-overlay').hidden=false;$('detail-body').innerHTML='<div class="empty">请先从修改任务中选择一份合同。<button class="btn" data-nav="overview">返回修改任务</button></div>';return;}
    try{if(state.selected!==route.id||!state.task)await selectTask(route.id,false);if(!current(t)||state.view!=='document')return;const doc=await json(`${pathTask(route.id)}/documents/${encodeURIComponent(route.document)}`);if(!current(t)||state.view!=='document')return;await showDetail(doc);if(route.tab==='review'&&current(t))await openReview(doc);}
    catch(e){if(current(t)&&e.name!=='AbortError'){$('detail-overlay').hidden=false;$('detail-body').innerHTML='<div class="empty">该合同不存在、无权访问或暂时不可用，请返回修改任务重试。</div>';}}
  }
  function formatSeconds(value){if(value==null||!Number.isFinite(Number(value)))return '—';const seconds=Math.max(0,Math.round(Number(value)));if(seconds<60)return `${seconds} 秒`;const minutes=Math.floor(seconds/60),rest=seconds%60;return rest?`${minutes} 分 ${rest} 秒`:`${minutes} 分`;}
  function formatChange(value){if(value==null||!Number.isFinite(Number(value)))return '—';const pct=Math.round(Number(value)*1000)/10;return `${pct>0?'+':''}${pct}%`;}
  function syncFirstRunGuide(){const el=$('first-run-guide');if(!el)return;
    const show=state.tasksLoaded&&!state.tasksFailed&&!state.guideDismissed&&!(state.tasks||[]).length&&!$('task-search').value.trim()&&!$('task-filter').value&&!$('task-guide-filter').value;
    show?el.removeAttribute('hidden'):el.setAttribute('hidden','');
  }
  function guideNameForTask(task){if(!task)return '—';if(task.legacy)return '遗留任务 · 未绑定指引';const id=task.guide_snapshot?.version_id;if(!id)return '未绑定指引';const item=(state.taskGuides||[]).find(guide=>guide.id===id);return `${item?.filename||'创建时的指引'}`;}
  function renderTaskGuideFilter(){const select=$('task-guide-filter');if(!select)return;const current=select.value,items=state.taskGuides||[];patchHTML(select,'<option value="">全部指引</option>'+items.map(guide=>`<option value="${esc(guide.id)}">${esc(guideDisplayName(guide))}${guide.built_in?'（内置）':''}</option>`).join(''));if(current&&items.some(guide=>guide.id===current))select.value=current;}
  // FL-D1039：并行 loadTaskGuides 成功路径也调 renderTaskRows——首载失败语义的空态
  // 「任务暂未加载」必须尊重 state.tasksFailed 不被「当前条件下没有任务」改写，失败与空账号可分辨。
  function renderTaskRows(){const items=state.tasks||[];if(!items.length&&state.tasksLoaded&&state.tasksFailed){patchHTML($('task-rows'),emptyRow(7,'任务暂未加载，请检查连接后刷新'));return;}patchHTML($('task-rows'),items.map(taskRow).join('')||emptyRow(7,'当前条件下没有任务'));}
  async function loadTaskGuides(quiet=false){if(state.auth.mode==='password'&&!state.auth.token)return;const t=ticket('task-guides');try{const payload=await json('/api/guides');if(!current(t))return;state.taskGuides=Array.isArray(payload.items)?payload.items:[];renderTaskGuideFilter();renderTaskRows();syncFirstRunGuide();if(state.task)renderTask();}catch(e){if(!current(t))return;if(!quiet&&e.code!=='404'&&e.code!=='CONNECTION')errorNotice(e);}}
  function evaluationCount(t){const dc=t?.delivery_counts||{};return (dc.evaluation_modified||0)+(dc.evaluation_modified_with_exceptions||0)+(dc.evaluation_unmodified||0);}
  function progressHTML(t) {const total=t?.total || 1;return [['p-done',t?taskMetrics(t).success:0],['p-fail',t?taskMetrics(t).anomaly:0],['p-excluded',t?.qualification_counts?.excluded_by_fund_type||0],['p-evaluation',evaluationCount(t)],['p-work',t?.processing || 0],['p-queue',t?.queued || 0]].map(([c,n])=>`<span class="${c}" style="width:${Math.min(100,100*n/total)}%"></span>`).join('');}
  function renderTask() {
    const t=state.task,pct=t?.total?Math.round(100*(t.completed)/t.total):0;
    patchHTML($('task-status'),t?badge(t.status):'');if($('task-object-title').textContent!==(t?.name || '尚未选择任务'))$('task-object-title').textContent=t?.name || '尚未选择任务';$('selected-task-title').textContent='逐合同明细';
    $('selected-task-subtitle').textContent=t?'按合同逐份查看接收、处理与交付状态；失败或异常行已高亮。':'从任务总览选择任务查看结果。';
    const dc=t?.delivery_counts||{};
    const guideMeta=$('task-guide-meta'),guideValue=$('task-guide-value');if(guideMeta)guideMeta.hidden=!t;if(guideValue)guideValue.textContent=t?guideNameForTask(t):'';
    $('progress-evaluation-legend').hidden=!evaluationCount(t);
    const anomaly=t?taskMetrics(t).anomaly:0;
    const processCounts=t?[['合同总数',t.total,'任务全部合同'],['已处理',t.completed,`已进入终态 · 交付完成 ${taskMetrics(t).success}`],['处理中',t.processing,'正在处理'],['排队',t.queued,'排队或等待重试'],['异常',anomaly,`失败 ${t.failed} · 接收失败 ${t.rejected}`],['整体进度',`${pct}%`,`${t.completed} / ${t.total} 份进入终态`]]:[];
    patchHTML($('overall-counts'),processCounts.map(([l,n,note])=>`<div class="mini-kpi" title="${esc(note)}"><label>${l}</label><b>${n}</b></div>`).join(''));
    for(const action of ['export-results']){const b=document.querySelector(`[data-action="${action}"]`);if(b)b.disabled=!t;}
    const dlAll=document.querySelector('[data-action="download-all"]');if(dlAll){const ready=!!t&&((t.completed||0)+(t.failed||0)>0);dlAll.removeAttribute('disabled');dlAll.setAttribute('aria-disabled',String(!ready));dlAll.title=ready?'':'当前尚无已出结果的合同；处理结束（含失败）后即可下载结果包';const dlHint=$('download-hint');if(dlHint)dlHint.hidden=!t||ready;}
     $('task-upload-label').textContent=t?`${t.uploaded} / ${t.total} 份已上传${t.rejected?` · ${t.rejected} 份接收失败`:''}${t.pending_upload?` · ${t.pending_upload} 份待补传`:''}`:'尚未选择任务';$('task-process-label').textContent=t?(['completed','completed_with_exceptions','failed'].includes(t.status)?(t.status==='failed'?'全部合同处理失败':t.status==='completed_with_exceptions'?'处理结束，含失败或异常合同':'全部处理结束'):t.status==='paused'?`任务已暂停${t.pause_reason?' · '+reason(t.pause_reason):''}`:`已完成 ${t.completed} / ${t.total} 份`):'尚未选择任务';{const id='overall-progress';patchHTML($(id),progressHTML(t));$(id).setAttribute('role','progressbar');$(id).setAttribute('aria-label','合同处理总进度');$(id).setAttribute('aria-valuemin','0');$(id).setAttribute('aria-valuemax','100');$(id).setAttribute('aria-valuenow',String(pct));}
     $('pause-btn').textContent=t?.status==='paused'?'继续任务':'暂停任务';$('pause-btn').disabled=!t||t.legacy||['completed','completed_with_exceptions','failed'].includes(t.status);$('recover-btn').disabled=!t||t.legacy||!(t.pending_upload+t.rejected)||state.uploading;
    {const select=$('task-select'),items=state.tasks.slice();if(t&&!items.some(x=>x.id===t.id))items.unshift(t);patchHTML(select,'<option value="">选择任务</option>'+items.map(x=>`<option value="${esc(x.id)}" ${x.id===state.selected?'selected':''}>${esc(x.name)}</option>`).join(''));}
  }
  function stopFeishuOAuth(){feishuOAuthEpoch++;clearInterval(feishuOAuthTimer);feishuOAuthTimer=null;feishuExpiresAt=0;$('feishu-oauth-qr').replaceChildren();$('feishu-oauth-link').removeAttribute('href');$('feishu-oauth-link').hidden=true;$('feishu-oauth-panel').hidden=true;$('feishu-oauth-btn').disabled=false;$('feishu-oauth-btn').textContent='扫码绑定飞书';$('feishu-unbind-confirm').hidden=true;}
  function renderFeishuBinding(binding){
    feishuBound=!!binding.bound;
    $('feishu-connect-card').dataset.state=feishuBound?'bound':'unbound';
    $('feishu-binding-badge').textContent=feishuBound?'已绑定':'未绑定';
    $('feishu-binding-state').textContent=feishuBound?'飞书已连接。现在可以在与 FundLex 机器人的私聊中发送合同，无需再次扫码。':'还未连接飞书。使用你本人的飞书扫码并确认授权，即可完成绑定。';
    $('feishu-oauth-btn').hidden=feishuBound;$('feishu-oauth-btn').disabled=false;
    $('feishu-unbind-btn').hidden=!feishuBound;
    if(feishuBound)stopFeishuOAuth();
  }
  async function loadFeishuBinding(){
    if(!state.cap||state.view!=='feishu')return;
    const t=ticket('feishu-binding');
    $('feishu-current-user').textContent=state.auth.user?.display_name||state.auth.user?.username||owner();
    $('feishu-binding-refresh').disabled=true;
    try{const binding=await json('/api/integrations/feishu/binding');if(!current(t)||state.view!=='feishu')return;renderFeishuBinding(binding);}
    catch(e){if(!current(t)||state.view!=='feishu'||e.name==='AbortError')return;stopFeishuOAuth();$('feishu-connect-card').dataset.state='error';$('feishu-binding-badge').textContent='读取失败';$('feishu-binding-state').textContent='暂时无法读取绑定状态，请刷新状态后重试。';$('feishu-oauth-btn').disabled=true;$('feishu-unbind-btn').hidden=true;}
    finally{if(current(t))$('feishu-binding-refresh').disabled=false;}
  }
  let modelProviders=[];
  const modelRoleName=prefix=>prefix==='primary'?'修改模型':'复核模型';
  const modelProviderLabel=id=>modelProviders.find(p=>p.id===id)?.label||id||'—';
  function modelRoleBadge(prefix){
    const role=(state.modelData||{})[prefix]||{};
    if(role.source!=='personal')return badge('','系统默认');
    return state.modelVerified[prefix]?badge('succeeded','自定义·已验证'):badge('paused','自定义·未验证');
  }
  function modelRoleSummary(prefix){
    const role=(state.modelData||{})[prefix]||{},personal=role.source==='personal';
    if(!personal)return `<dl class="model-role-summary"><dt>使用方式</dt><dd>系统默认</dd><dt>说明</dt><dd>由管理员统一配置，可直接使用。</dd></dl>`;
    return `<dl class="model-role-summary"><dt>供应商</dt><dd>${esc(modelProviderLabel(role.provider))}</dd><dt>模型</dt><dd>${esc(role.model||'—')}</dd><dt>访问密钥</dt><dd>${role.api_key_set?'已保存（加密，不回显）':'未设置'}</dd><dt>验证状态</dt><dd>${state.modelVerified[prefix]?badge('succeeded','已验证'):'尚未验证'}</dd></dl>`;
  }
  function modelRoleCard(prefix){
    const role=(state.modelData||{})[prefix]||{},personal=role.source==='personal',editing=state.modelEdit===prefix;
    const head=`<div class="model-status-row"><span class="model-role-icon" aria-hidden="true"><svg><use href="#${prefix==='primary'?'i-file':'i-search'}"/></svg></span><div class="model-role-title"><h3>${modelRoleName(prefix)}</h3><p>${prefix==='primary'?'负责起草合同的修改内容。':'负责逐项复查修改是否正确，可用不同供应商的模型。'}</p></div><span class="model-role-badge">${modelRoleBadge(prefix)}</span></div>`;
    if(!editing)return `<div class="card model-role-card" data-model-role="${prefix}">${head}${modelRoleSummary(prefix)}<div class="model-card-actions">${personal?`<button class="btn btn-sm btn-quiet" type="button" data-action="model-settings-reset" data-model-reset="${prefix}">恢复系统默认</button>`:''}<button class="btn btn-sm btn-primary" type="button" data-model-edit="${prefix}">修改配置</button></div></div>`;
    return `<div class="card model-role-card is-editing" data-model-role="${prefix}">${head}
      <form id="model-settings-form" class="model-edit-form">
      <div class="model-edit-field"><span class="model-field-label">使用方式</span><div class="model-segmented" role="radiogroup" aria-label="使用方式"><input id="model-${prefix}-source" type="hidden" value="${personal?'personal':'system'}"><button type="button" role="radio" aria-checked="${personal?'false':'true'}" data-model-source-opt="system">使用系统默认</button><button type="button" role="radio" aria-checked="${personal?'true':'false'}" data-model-source-opt="personal">使用自己的模型</button></div></div>
      <p id="model-${prefix}-default" class="subnote" ${personal?'hidden':''}>系统模型由管理员统一配置。</p>
      <div id="model-${prefix}-personal" class="form-stack" ${personal?'':'hidden'}>
      <label>供应商<select id="model-${prefix}-provider">${modelProviders.map(p=>`<option value="${esc(p.id)}" ${p.id===(role.provider||'openai')?'selected':''}>${esc(p.label)}</option>`).join('')}</select></label>
      <label id="model-${prefix}-address-label" ${role.provider==='custom'?'':'hidden'}>服务地址<input id="model-${prefix}-base_url" type="url" value="${esc(role.base_url||'')}" placeholder="https://你的服务商地址/v1"><span class="subnote">仅其他兼容服务需要填写，由供应商提供。</span></label>
      <label>访问密钥（API Key）<input id="model-${prefix}-api_key" type="password" autocomplete="new-password" maxlength="4096" ${personal&&role.connection_id?'':'required'} placeholder="${personal&&role.api_key_set?'已保存；留空保留，填写可更换':'粘贴供应商提供的访问密钥'}"></label>
      <input id="model-${prefix}-connection_id" type="hidden" value="${esc(role.connection_id||'')}">
      <label>模型<input id="model-${prefix}-model" list="model-${prefix}-suggestions" value="${personal?esc(role.model||''):''}" placeholder="选择建议或填写供应商提供的模型名称"><datalist id="model-${prefix}-suggestions"></datalist></label>
      <p id="model-${prefix}-deprecated" class="subnote model-deprecated-hint" hidden></p>
      </div>
      
      <div class="model-card-actions"><button class="btn btn-sm" type="button" data-model-test="${prefix}">验证连接</button><button class="btn btn-sm btn-primary" type="button" data-action="model-settings-save" data-model-save="${prefix}">保存</button><button class="btn btn-sm btn-quiet" type="button" data-model-edit-cancel>取消</button></div>
      <p id="model-${prefix}-status" class="model-status-msg" role="status" aria-live="polite"></p></form></div>`;
  }
  function refreshModelRole(prefix){
    const sourceInput=$(`model-${prefix}-source`);
    const seg=sourceInput&&sourceInput.closest('.model-segmented');
    if(seg)seg.querySelectorAll('[data-model-source-opt]').forEach(b=>{const on=b.dataset.modelSourceOpt===sourceInput.value;b.setAttribute('aria-checked',on?'true':'false');b.classList.toggle('is-active',on);});
    const personal=sourceInput.value==='personal';
    $(`model-${prefix}-personal`).hidden=!personal;$(`model-${prefix}-default`).hidden=personal;
    const provider=modelProviders.find(p=>p.id===$(`model-${prefix}-provider`).value);
    $(`model-${prefix}-address-label`).hidden=provider?.id!=='custom';
    $(`model-${prefix}-suggestions`).innerHTML=(provider?.models||[]).map(m=>`<option value="${esc(m)}">`).join('');
    const retiredHint=$(`model-${prefix}-deprecated`);const retired=provider?.deprecated_models||[];
    retiredHint.hidden=!retired.length;
    retiredHint.innerHTML='';
    $(`model-${prefix}-personal`).querySelectorAll('input,select,button').forEach(n=>{n.disabled=!personal;});
    $(`model-${prefix}-model`).required=personal;
    $(`model-${prefix}-base_url`).required=personal&&provider?.id==='custom';
    $(`model-${prefix}-api_key`).required=personal&&!$(`model-${prefix}-connection_id`).value;
  }
  function modelRolePayload(prefix){
    if($(`model-${prefix}-source`).value==='system')return {source:'system'};
    return {source:'personal',provider:$(`model-${prefix}-provider`).value,
      model:$(`model-${prefix}-model`).value.trim(),api_key:$(`model-${prefix}-api_key`).value,
      connection_id:$(`model-${prefix}-connection_id`).value,
      base_url:$(`model-${prefix}-provider`).value==='custom'?$(`model-${prefix}-base_url`).value.trim():''};
  }
  function modelSavedPayload(prefix){
    const role=(state.modelData||{})[prefix]||{};
    if(role.source!=='personal')return {source:'system'};
    return {source:'personal',provider:role.provider||'openai',model:role.model||'',api_key:'',connection_id:role.connection_id||'',base_url:role.provider==='custom'?(role.base_url||''):''};
  }
  function renderModelSettings(data){
    const body=$('model-settings-body');if(!body)return;
    state.modelData=data;modelProviders=data.providers||[];
    $('model-copy-btn').disabled=false;
    if(state.modelEdit&&!['primary','review'].includes(state.modelEdit))state.modelEdit=null;
    {const source=$('model-settings-source');if(source)source.textContent=data.source==='personal'?'已启用自定义模型':'正在使用系统默认模型';}
    body.classList.remove('subnote');
    body.innerHTML=`<p class="subnote model-page-note">两个模型分别负责修改合同与复核结果，配置只影响你之后新建的任务。</p>${data.legacy_preferences?`<div class="model-alert" role="status"><strong>检测到旧版保存设置</strong><span>重新保存一次即可切换到新配置；新配置支持修改模型与复核模型分开设置。</span></div>`:''}${data.config_error?`<div class="model-alert is-error" role="alert"><strong>读取模型密钥时出错</strong><span>暂时无法读取已保存的密钥，请稍后重试；反复出现请联系管理员。</span></div>`:''}<div class="model-roles">${modelRoleCard('primary')}${modelRoleCard('review')}</div>`;
    if(state.modelEdit){refreshModelRole(state.modelEdit);if(state.modelCopyFrom){const from=(state.modelData||{})[state.modelCopyFrom]||{};const target=state.modelEdit;$(`model-${target}-source`).value=from.source==='personal'?'personal':'system';if(from.source==='personal'){const provider=modelProviders.find(p=>p.id===from.provider)?from.provider:'openai';$(`model-${target}-provider`).value=provider;$(`model-${target}-base_url`).value=from.base_url||'';$(`model-${target}-model`).value=from.model||'';$(`model-${target}-connection_id`).value=from.connection_id||'';$(`model-${target}-api_key`).value='';}refreshModelRole(target);$(`model-${target}-status`).textContent='已复制修改模型的配置，请保存；复核仍单独进行。';state.modelCopyFrom=null;}}
  }
  async function loadModelSettings(quiet=false){
    if(!state.cap||state.view!=='models')return;
    const t=ticket('model-settings');
    try{const data=await json('/api/settings/model');if(!current(t)||state.view!=='models')return;renderModelSettings(data);}
    catch(e){if(!current(t)||state.view!=='models')return;const body=$('model-settings-body');if(body){body.classList.add('subnote');body.innerHTML=`<div class="model-alert is-error" role="alert"><strong>模型配置读取失败</strong><span>暂时无法读取配置，请稍后重试；反复出现请联系管理员。</span></div><button class="btn btn-sm" type="button" data-action="model-retry">重新读取</button>`;}$('model-settings-source').textContent='读取失败';$('model-copy-btn').disabled=true;if(!quiet&&e.code!=='404')errorNotice(e);}
  }
  async function saveModelSettings(prefix){
    const form=$('model-settings-form');if(!form)return;
    if(!form.reportValidity())return;
    const t=ticket('model-settings-save');
    try{const data=await json('/api/settings/model',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({primary:prefix==='primary'?modelRolePayload('primary'):modelSavedPayload('primary'),review:prefix==='review'?modelRolePayload('review'):modelSavedPayload('review')})});if(!current(t)||state.view!=='models')return;state.modelEdit=null;renderModelSettings(data);toast('配置已保存；保存不代表已验证连接，仅用于新建合同修改任务。');}
    catch(e){if(current(t))errorNotice(e,'模型配置保存未完成：');}
  }
  document.addEventListener('click',async e=>{
    const resetBtn=e.target.closest('[data-action="model-settings-reset"]');if(!resetBtn)return;
    const prefix=resetBtn.dataset.modelReset==='review'?'review':'primary';
    if(!confirm(`恢复${modelRoleName(prefix)}为系统默认？仅影响之后新建的任务。`))return;
    const t=ticket('model-settings');
    try{const data=await json('/api/settings/model',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({primary:prefix==='primary'?{source:'system'}:modelSavedPayload('primary'),review:prefix==='review'?{source:'system'}:modelSavedPayload('review')})});if(current(t)&&state.view==='models'){state.modelEdit=null;renderModelSettings(data);}}
    catch(error){if(current(t))errorNotice(error,'恢复系统默认失败：');}
  });
  document.addEventListener('click',e=>{
    const sourceOpt=e.target.closest('[data-model-source-opt]');
    if(sourceOpt){const card=sourceOpt.closest('[data-model-role]');if(card){const prefix=card.dataset.modelRole;$(`model-${prefix}-source`).value=sourceOpt.dataset.modelSourceOpt;state.modelVerified[prefix]=false;const statusNode=$(`model-${prefix}-status`);if(statusNode){statusNode.dataset.tone='';statusNode.textContent='配置已更改，尚未验证。';}refreshModelRole(prefix);}return;}
    const editBtn=e.target.closest('[data-model-edit]');
    if(editBtn){state.modelEdit=editBtn.dataset.modelEdit;renderModelSettings(state.modelData||{});$(`model-${state.modelEdit}-source`)?.closest('.model-segmented')?.querySelector('[aria-checked="true"]')?.focus();return;}
    if(e.target.closest('[data-model-edit-cancel]')){state.modelEdit=null;renderModelSettings(state.modelData||{});}
  });
  document.addEventListener('input',e=>{
    const card=e.target.closest('.model-edit-form');if(!card)return;
    const prefix=card.closest('[data-model-role]')?.dataset.modelRole;if(!prefix)return;
    state.modelVerified[prefix]=false;
    const st=$(`model-${prefix}-status`);st.dataset.tone='';st.textContent='配置已更改，尚未验证。';
  });
  document.addEventListener('change',e=>{
    if(e.target.id==='gd-diff-from'||e.target.id==='gd-diff-to'){const d=state.guideDiff;if(!d||d.prog)return;if(e.target.id==='gd-diff-from')d.from=e.target.value;else d.to=e.target.value;return;}if(e.target.id==='review-author-filter'){const v=e.target.value||'';state.reviewAuthorFilter=v;document.querySelectorAll('.rev-item').forEach(li=>{const isSrc=li.dataset.revSrc==='1';li.hidden=isSrc?(!v||li.dataset.revAuthor!==v):(!!v&&li.dataset.revAuthor!==v);});const visible=[...document.querySelectorAll('.rev-item')].filter(li=>!li.hidden).length;const isSrcOnly=v&&![...document.querySelectorAll('.rev-item[data-rev-item]')].some(li=>li.dataset.revAuthor===v);const t=document.querySelector('.review-list-title');if(t)t.textContent=(v&&isSrcOnly)?`${v}的修订 · ${visible} 条（来自原文件，已并入正文）`:`改动清单 · ${visible} / ${state.review?.revisions?.length||0} 条`;return;}
if(e.target.id==='gd-diff-filter'){const d=state.guideDiff;if(d){d.filter=e.target.value||'';d.cursor=-1;gdRenderRail(d);}return;}if(e.target.id==='gd-diff-show-sources'){const d=state.guideDiff;if(d){d.showSources=e.target.checked;if(d.td&&d.view!=='classic')gdRenderPanes(d);}return;}
    const card=e.target.closest('.model-edit-form');if(!card)return;
    const prefix=card.closest('[data-model-role]')?.dataset.modelRole;if(!prefix)return;
    if(['provider','base_url'].includes(e.target.id.replace(`model-${prefix}-`,''))){$(`model-${prefix}-connection_id`).value='';$(`model-${prefix}-api_key`).value='';}
    state.modelVerified[prefix]=false;
    const st=$(`model-${prefix}-status`);st.dataset.tone='';st.textContent='配置已更改，尚未验证。';
    refreshModelRole(prefix);
  });
  document.addEventListener('click',async e=>{
    if(e.target.closest('[data-action="model-retry"]')){loadModelSettings(true);return;}
    if(e.target.closest('[data-action="model-copy-primary"]')){
      if(!state.modelData){flash('配置尚未读取完成，请稍后重试。');return;}
      state.modelEdit='review';state.modelCopyFrom='primary';
      renderModelSettings(state.modelData);$(`model-review-source`)?.closest('.model-segmented')?.querySelector('[aria-checked="true"]')?.focus();return;
    }
    const button=e.target.closest('[data-model-test]');if(!button)return;
    const prefix=button.dataset.modelTest,t=ticket(`model-test-${prefix}`);
    const status=$(`model-${prefix}-status`);
    // 系统默认模型由服务端托管连接、无需也不准验（后端 MODEL_TEST_PERSONAL_ONLY 语义对前端封闭化）
    if((modelRolePayload(prefix)||{}).source!=='personal'){
      if(status){status.dataset.tone='ok';status.textContent='系统默认模型由服务端托管，无需验证；只有自定义密钥连接才需要点这个按钮。';}
      return;
    }
    status.dataset.tone='pending';status.textContent='正在连接供应商，通常几秒钟出结果…';button.disabled=true;
    try{const result=await json('/api/settings/model/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(modelRolePayload(prefix))});if(current(t)&&state.view==='models'){if(result&&result.ok===false){state.modelVerified[prefix]=false;status.dataset.tone='error';status.textContent=`连接验证未通过：${String(result.message||'').trim()||'请检查密钥与模型名后重试。'}`;}else{state.modelVerified[prefix]=true;status.dataset.tone='ok';status.textContent=String((result&&result.message)||'').trim()||'连接验证通过，可以保存使用了。';}}}
    catch(error){if(current(t)){state.modelVerified[prefix]=false;status.dataset.tone='error';const detail=String(error&&error.raw||'').trim();status.textContent=`连接验证未通过：${detail||'请检查网络、密钥与模型名后重试。'}`;}}
    finally{if(button.isConnected)button.disabled=false;}
  });
  document.addEventListener('fundlex:view',e=>{
    if(e.detail==='models')return;
    ['primary','review'].forEach(prefix=>{
      state.tokens[`model-test-${prefix}`]=(state.tokens[`model-test-${prefix}`]||0)+1;
      const input=$(`model-${prefix}-api_key`);if(input)input.value='';
    });
  });
  document.addEventListener('fundlex:identity-reset',()=>{
    modelProviders=[];
    const body=$('model-settings-body');
    if(body)body.textContent='正在读取当前账号的模型配置…';
    const source=$('model-settings-source');
    if(source)source.textContent='读取中';
    const copyBtn=$('model-copy-btn');
    if(copyBtn)copyBtn.disabled=true;
  });
  async function startFeishuOAuth(){
    if(feishuBound)return;
    state.tokens['feishu-binding']=(state.tokens['feishu-binding']||0)+1;
    stopFeishuOAuth();const epoch=state.epoch,session=feishuOAuthEpoch;
    const valid=()=>identityCurrent(epoch)&&session===feishuOAuthEpoch&&state.view==='feishu';
    const button=$('feishu-oauth-btn'),panel=$('feishu-oauth-panel'),message=$('feishu-oauth-message'),link=$('feishu-oauth-link');
    button.disabled=true;panel.hidden=false;message.textContent='正在生成个人二维码…';
    try{
      const result=await json('/api/integrations/feishu/oauth/start',{method:'POST'});if(!valid())return;
      const url=new URL(result.authorization_url);
      if(url.protocol!=='https:'||!['accounts.feishu.cn','open.feishu.cn'].includes(url.hostname))throw new Error('授权地址无效，请稍后重试。');
      if(result.qr_png?.startsWith('data:image/png;base64,')){const img=document.createElement('img');img.src=result.qr_png;img.alt='用飞书扫描此二维码完成账号绑定';img.width=650;img.height=650;$('feishu-oauth-qr').replaceChildren(img);}
      else message.textContent='二维码暂不可用，请使用下方授权链接。';
      link.href=url.href;link.hidden=false;feishuExpiresAt=Number(result.expires_at||0)*1000;
      button.textContent='重新生成二维码';
      let checking=false,lastCheck=0;
      const tick=async()=>{
        if(!valid())return;
        const seconds=Math.ceil((feishuExpiresAt-Date.now())/1000);
        if(seconds<=0){stopFeishuOAuth();panel.hidden=false;button.textContent='重新生成二维码';message.textContent='二维码已过期，请重新生成后扫码。';return;}
        message.textContent=`请用飞书扫码并确认授权 · ${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')} 后过期`;
        if(checking||Date.now()-lastCheck<2500)return;
        checking=true;lastCheck=Date.now();
        try{const binding=await json('/api/integrations/feishu/binding');if(!valid())return;if(binding.bound){renderFeishuBinding(binding);$('feishu-binding-message').textContent='绑定成功，可以前往飞书使用。';flash('飞书账号绑定成功。');}}
        catch(e){if(valid()&&e.name!=='AbortError')message.textContent='暂时无法确认绑定结果，请检查网络或点击刷新状态。';}
        finally{checking=false;}
      };
      feishuOAuthTimer=setInterval(tick,1000);tick();
    }catch(e){if(valid()&&e.name!=='AbortError'){message.textContent=humanErrorText(e,'二维码生成失败，请稍后重试。');button.textContent='重新生成二维码';}}
    finally{if(valid())button.disabled=false;}
  }
  async function revokeFeishuBinding(){
    const t=ticket('feishu-revoke'),button=document.querySelector('[data-action="feishu-unbind-confirm"]');button.disabled=true;
    try{await json('/api/integrations/feishu/binding',{method:'DELETE'});if(!current(t))return;stopFeishuOAuth();renderFeishuBinding({bound:false});$('feishu-binding-message').textContent='已解除绑定。需要时可重新扫码连接。';}
    catch(e){if(current(t)&&e.name!=='AbortError')$('feishu-binding-message').textContent='解除绑定失败，请稍后重试。';}
    finally{if(current(t))button.disabled=false;}
  }
  // ---- Flywheel: own-tenant Feishu app onboarding (FL-D780..784) ----
  const feishuApp={data:null,timer:null,localStep:1,localPanel:null,reenterFrom:null,code:'',codeExpiry:0,busy:false,confirmRemove:false};
  async function feishuAppRequest(path,options={}){
    if(!state.auth.token&&!owner())throw new Error('请先登录后再连接飞书。');
    const headers=new Headers(options.headers||{});
    if(state.auth.token)headers.set('Authorization',`Bearer ${state.auth.token}`);
    if(owner())headers.set('X-FundLex-User',owner());
    let response;try{response=await fetch(path,{...options,headers,cache:'no-store'});}catch{throw new Error('网络连接中断，请检查网络后重试。');}
    if(response.status===401&&state.auth.mode==='password'){handleSessionExpired();throw new Error('登录状态已失效，请重新登录。');}
    let payload=null;try{payload=await response.json();}catch{}
    if(!response.ok){
      const detail=payload&&payload.detail;const message=(payload&&payload.message)||(typeof detail==='string'?detail:(detail&&detail.message))||'请求未完成，请稍后重试。';
      const error=new Error(message);error.detail=payload||null;error.code=response.status;throw error;
    }
    return payload;
  }
  function feishuAppStep(data){
    if(feishuApp.localPanel)return feishuApp.localPanel;
    if(!data||!data.configured)return feishuApp.localStep;
    if(data.stage==='needs_attention')return 3;
    return 4;
  }
  function feishuAppStopPoll(){if(feishuApp.timer){clearInterval(feishuApp.timer);feishuApp.timer=null;}}
  function feishuAppPoll(){feishuAppStopPoll();feishuApp.timer=setInterval(()=>{if(feishuAppStep(feishuApp.data)===4)loadFeishuApp(true);},3000);}
  function feishuAppApplyLinks(guide){
    if(!guide)return;
    $('feishu-app-create-link').href=guide.create_app;
    $('feishu-app-credentials-link').href=guide.create_app;
    $('feishu-app-link-permission').href=guide.permission;
    $('feishu-app-link-bot').href=guide.bot;
    $('feishu-app-link-event').href=guide.event;
    $('feishu-app-link-version').href=guide.version;
  }
  function feishuAppRenderScopes(data){
    const guide=data.guide||{};const list=$('feishu-app-scopes');if(!list)return;
    const checks=new Map((data.checks||[]).map(c=>[c.key,c.ok]));
    const unknown=!data.scopes_checked;
    list.replaceChildren();(guide.required_scopes||[]).forEach(scope=>{
      const li=document.createElement('li');const ok=checks.get(scope.key);
      const mark=document.createElement('span');mark.className=ok===true?'scope-ok':(ok===false?'scope-missing':'');mark.textContent=ok===true?'✓':(ok===false?'待添加':'•');
      const code=document.createElement('code');code.textContent=scope.key;
      const label=document.createElement('span');label.textContent=scope.label;
      li.append(mark,code,label);list.append(li);
    });
    const setState=(name,value)=>{const el=document.querySelector(`.feishu-config-state[data-check="${name}"]`);if(!el)return;if(value===null){delete el.dataset.ok;el.textContent='待验证';return;}el.dataset.ok=String(value);el.textContent=value?'已完成':'待完成';};
    if((guide.required_scopes||[]).length)setState('scopes',unknown?null:(guide.required_scopes||[]).every(s=>checks.get(s.key)===true));
    setState('bot',checks.get('bot')===true);
  }
  function feishuAppRender(data,quiet){
    feishuApp.data=data;
    const guide=data.guide;feishuAppApplyLinks(guide);
    const configured=!!data.configured;
    $('feishu-app-entry').hidden=configured;
    $('feishu-app-summary').hidden=!configured;
    if(configured){
      const stage=data.stage;const bound=!!(data.binding&&data.binding.bound);
      const active=stage==='active'&&bound;
      $('feishu-app-summary-title').textContent=active?'已连接你自己的飞书企业':(stage==='needs_attention'?'应用还需要完成配置':(stage==='active'?'已收到你的消息，等待绑定':'正在连接你自己的飞书企业'));
      const bits=[];if(data.bot_name)bits.push(data.bot_name);if(data.tenant_name)bits.push(data.tenant_name);
      bits.push(active?'可以私聊机器人处理合同':(stage==='needs_attention'?'点“查看连接”继续完成':(stage==='active'?'在飞书私聊里发送向导里的绑定码':'等待你在飞书里发消息')));
      $('feishu-app-summary-text').textContent=bits.join(' · ');
      $('feishu-app-summary').dataset.stage=stage;
    }
    if(data.binding&&data.binding.bound)feishuAppStopPoll();
    if($('feishu-app-wizard').hidden)return;
    feishuAppRenderPanel(data);
    if(!quiet)feishuAppPoll();
    if(feishuAppStep(data)===4&&data.first_event_at&&!(data.binding&&data.binding.bound))feishuAppEnsureCode();
  }
  function feishuAppRenderPanel(data){
    const step=feishuAppStep(data);
    document.querySelectorAll('#feishu-app-wizard [data-panel]').forEach(panel=>{panel.hidden=Number(panel.dataset.panel)!==step;});
    document.querySelectorAll('#feishu-app-steps li').forEach(li=>{const n=Number(li.dataset.step);li.dataset.state=n<step?'done':(n===step?'active':'todo');});
    const botName=(data.bot_name||'FundLex');
    $('feishu-app-bot-name').textContent=botName;
    $('feishu-app-view-config').hidden=!(step===4&&data.configured);
    $('feishu-app-back-test').hidden=!(step===3&&data.configured);
    if(step===3){
      feishuAppRenderScopes(data);
      if(data.error&&data.error.message)feishuAppShowError('recheck',{message:data.error.message,detail:{detail:data.error.detail||'',link:data.error.link||''}});
      else $('feishu-app-recheck-error').hidden=true;
      const appName=data.app_name||data.app_id||'';
      const botName2=data.bot_name||'';
      const appText=appName?(botName2&&botName2!==appName?`当前应用：${appName}（机器人：${botName2}）`:`当前应用：${appName}`):'正在读取应用状态…';
      $('feishu-app-verify-summary').textContent=data.scopes_checked?appText:`${appText}。这个应用未授予「应用信息读取」权限，权限清单无法自动核对；按下面清单逐项确认后，收到消息即证明生效。`;
      const eventState=document.querySelector('.feishu-config-state[data-check="event"]');
      if(eventState){eventState.dataset.ok='false';eventState.textContent=data.first_event_at?'已验证':'待验证';if(data.first_event_at)eventState.dataset.ok='true';}
    }
    if(step!==4)return;
    const connected=!!data.runtime_connected;const gotMessage=!!data.first_event_at;
    const bound=!!(data.binding&&data.binding.bound);
    const conn=$('feishu-app-conn-state');
    if(bound){conn.dataset.state='connected';$('feishu-app-conn-title').textContent='已连接，绑定完成';$('feishu-app-conn-text').textContent='可以关闭本页，在飞书私聊机器人使用。';}
    else if(gotMessage){conn.dataset.state='connected';$('feishu-app-conn-title').textContent='已收到你的消息，连接正常';$('feishu-app-conn-text').textContent='最后一步：把下面的绑定码发给同一个机器人。';}
    else if(connected){conn.dataset.state='waiting';$('feishu-app-conn-title').textContent='已连接，等待你发消息';$('feishu-app-conn-text').textContent=`打开飞书，搜索「${botName}」并发送一句「你好」。`;}
    else {conn.dataset.state='waiting';$('feishu-app-conn-title').textContent='正在建立连接…';$('feishu-app-conn-text').textContent='保存后一般 5 秒内完成。如果超过 1 分钟，请回到第 3 步检查「长连接」和「发布版本」。';}
    $('feishu-app-binding').hidden=!(gotMessage&&!bound);
    $('feishu-app-done').hidden=!bound;
    if(bound)$('feishu-app-done-text').textContent=`${botName} 已连接到当前 FundLex 账号，可以在飞书私聊发送 DOCX 合同或输入「菜单」。`;
    if(gotMessage&&!bound){$('feishu-app-code').textContent=feishuApp.code||'……';feishuAppRenderExpiry();}
  }
  function feishuAppRenderExpiry(){
    const el=$('feishu-app-code-expiry');if(!el)return;
    if(!feishuApp.codeExpiry){el.textContent='';return;}
    const left=Math.max(0,Math.round((feishuApp.codeExpiry-Date.now())/1000));
    el.textContent=left>0?`绑定码 ${Math.floor(left/60)} 分 ${String(left%60).padStart(2,'0')} 秒内有效；过期后点“换一个”。`:'绑定码已过期，请点“换一个”。';
  }
  async function feishuAppEnsureCode(){
    if(feishuApp.busy)return;
    if(feishuApp.code&&feishuApp.codeExpiry-Date.now()>30000){feishuAppRenderExpiry();return;}
    feishuApp.busy=true;
    try{
      const result=await feishuAppRequest('/api/integrations/feishu/binding-code',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ttl_seconds:1800})});
      feishuApp.code=result.code||'';feishuApp.codeExpiry=Number(result.expires_at||0)*1000;
      $('feishu-app-code').textContent=feishuApp.code||'……';feishuAppRenderExpiry();
    }catch(e){$('feishu-app-conn-text').textContent='绑定码生成失败，请稍后重试或刷新本页。';}
    finally{feishuApp.busy=false;}
  }
  async function loadFeishuApp(quiet=false){
    if(!quiet){feishuApp.code='';feishuApp.codeExpiry=0;}
    try{const data=await feishuAppRequest('/api/integrations/feishu/app');if(state.view!=='feishu')return;feishuAppRender(data,quiet);}
    catch(e){if(state.view!=='feishu')return;if(!quiet&&(state.auth.token||owner()))flash(humanErrorText(e,'读取飞书企业连接失败，请稍后重试。'));}
  }
  function openFeishuAppWizard(){
    stopFeishuOAuth();
    feishuApp.localStep=1;feishuApp.localPanel=null;feishuApp.reenterFrom=null;feishuAppStopPoll();
    $('feishu-app-wizard').hidden=false;
    feishuAppRenderPanel(feishuApp.data||{configured:false,stage:'no_app'});
    loadFeishuApp();
    $('feishu-app-wizard').scrollIntoView({block:'start',behavior:'smooth'});
  }
  function closeFeishuAppWizard(){
    feishuAppStopPoll();$('feishu-app-wizard').hidden=true;feishuApp.localPanel=null;feishuApp.reenterFrom=null;
    feishuApp.confirmRemove=false;
    const remove=$('feishu-app-remove');
    if(remove){remove.textContent='移除这个应用';remove.dataset.confirm='0';}
    $('feishu-app-error').hidden=true;
    $('feishu-app-recheck-error').hidden=true;
  }
  function feishuAppShowError(target,error){
    const box=$(target==='recheck'?'feishu-app-recheck-error':'feishu-app-error');
    const title=$(target==='recheck'?'feishu-app-recheck-error-title':'feishu-app-error-title');
    const text=$(target==='recheck'?'feishu-app-recheck-error-text':'feishu-app-error-text');
    const link=$(target==='recheck'?'feishu-app-recheck-error-link':'feishu-app-error-link');
    const detail=error&&error.detail;
    title.textContent=humanErrorText(error,'验证未通过');
    const raw=detail&&typeof detail==='object'?(detail.detail||''):(typeof detail==='string'?detail:'');
    const extra=/^[A-Z][A-Z0-9_.-]{1,96}$/.test(raw)?'':raw;
    text.textContent=extra||'请按提示修改后重试。';
    const href=detail&&typeof detail==='object'?(detail.link||''):'';
    if(href){link.href=href;link.hidden=false;}else{link.hidden=true;}
    box.hidden=false;
  }
  async function feishuAppSubmit(event){
    event.preventDefault();
    const id=$('feishu-app-id').value.trim(),secret=$('feishu-app-secret').value.trim();
    $('feishu-app-error').hidden=true;
    if(!id||!secret){feishuAppShowError('credentials',{message:'请填写 App ID 和 App Secret'});return;}
    const button=$('feishu-app-submit');const label=button.textContent;button.disabled=true;button.textContent='正在向飞书验证…';
    try{
      const data=await feishuAppRequest('/api/integrations/feishu/app/credentials',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({app_id:id,app_secret:secret})});
      $('feishu-app-secret').value='';
      feishuApp.localPanel=null;feishuApp.reenterFrom=null;
      feishuAppRender(data);
      const verification=data.verification||{};
      if(data.stage==='needs_attention'){
        feishuApp.localStep=3;feishuAppRenderPanel(data);
        flash('凭证已保存。还有配置项需要完成。');
      }else{
        feishuApp.localStep=4;feishuAppRenderPanel(data);
        flash(verification.scopes_checked?'凭证验证通过，权限和机器人都已就绪。':'凭证验证通过。');
      }
    }catch(e){feishuAppShowError('credentials',e);}
    finally{button.disabled=false;button.textContent=label;}
  }
  async function feishuAppRecheck(){
    const button=$('feishu-app-recheck');const label=button.textContent;button.disabled=true;button.textContent='正在检测…';
    $('feishu-app-recheck-error').hidden=true;
    try{
      const data=await feishuAppRequest('/api/integrations/feishu/app/verify',{method:'POST'});
      feishuApp.localPanel=null;
      feishuAppRender(data);
      if(data.stage==='needs_attention'){
        const missing=(data.missing_scopes||[]).length;const checks=data.checks||[];
        const botOk=(checks.find(c=>c.key==='bot')||{}).ok;
        feishuAppShowError('recheck',{message:missing?`还缺少 ${missing} 个权限`:'机器人还没有启用或版本未发布',detail:{detail:missing?'请按上面标黄的权限逐项添加，然后重新发布版本。':'请在「机器人」页启用机器人，并在「版本管理与发布」创建版本、申请发布。',link:data.guide&&(missing?data.guide.permission:data.guide.bot)}});
      }else if(data.scopes_checked){
        flash('配置齐全，正在建立连接。');
      }else{
        flash('已重新检测。没有「应用信息读取」权限时无法自动核对权限清单，请在飞书里给机器人发一句话确认。');
      }
    }catch(e){feishuAppShowError('recheck',e);}
    finally{button.disabled=false;button.textContent=label;}
  }
  function copyText(text,message){
    const done=()=>flash(message||'已复制。');
    if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(text).then(done).catch(()=>copyFallback(text,done));return;}
    copyFallback(text,done);
  }
  function copyFallback(text,done){
    const area=document.createElement('textarea');area.value=text;area.setAttribute('readonly','');area.style.position='fixed';area.style.opacity='0';document.body.append(area);area.select();
    try{document.execCommand('copy');done();}catch{flash('复制失败，请手动选择文本复制。');}
    area.remove();
  }
  async function feishuAppNewCode(){
    feishuApp.code='';feishuApp.codeExpiry=0;
    await feishuAppEnsureCode();
    flash('已生成新的绑定码。');
  }
  async function feishuAppRemove(){
    const button=$('feishu-app-remove');
    if(button.dataset.confirm!=='1'){button.dataset.confirm='1';button.textContent='再点一次确认移除';return;}
    button.disabled=true;
    try{
      const data=await feishuAppRequest('/api/integrations/feishu/app',{method:'DELETE'});
      feishuApp.code='';feishuApp.codeExpiry=0;feishuApp.localStep=1;
      feishuAppRender(data);feishuAppRenderPanel(data);
      flash('已移除这个应用。');
      button.textContent='移除这个应用';button.dataset.confirm='0';
    }catch(e){flash(humanErrorText(e,'移除失败，请稍后重试。'));}
    finally{button.disabled=false;}
  }
  document.addEventListener('fundlex:view',e=>{if(e.detail!=='feishu'){stopFeishuOAuth();state.tokens['feishu-binding']=(state.tokens['feishu-binding']||0)+1;$('feishu-binding-refresh').disabled=false;closeFeishuAppWizard();}});
  document.addEventListener('fundlex:identity-reset',()=>{stopFeishuOAuth();feishuBound=false;$('feishu-connect-card').dataset.state='loading';$('feishu-binding-badge').textContent='读取中';$('feishu-binding-state').textContent='正在读取绑定状态…';$('feishu-current-user').textContent='—';$('feishu-binding-message').textContent='';$('feishu-unbind-btn').hidden=true;$('feishu-oauth-btn').hidden=false;$('feishu-oauth-btn').disabled=true;document.querySelector('[data-action="feishu-unbind-confirm"]').disabled=false;closeFeishuAppWizard();feishuApp.data=null;feishuApp.code='';feishuApp.codeExpiry=0;feishuApp.localStep=1;feishuApp.confirmRemove=false;$('feishu-app-entry').hidden=false;$('feishu-app-summary').hidden=true;});
  async function loadCapabilities() {
    const t=ticket('cap'),wasReady=!!state.cap;
    try{
      const cap=await json('/api/capabilities');if(!current(t))return;
      state.auth.mode=cap.auth_mode||'dev';state.auth.loginRequired=!!cap.login_required;state.auth.registrationOpen=!!cap.registration_open;
      if(state.auth.mode==='password'){
        // FL-D1043：未登录分支必须撤回落网守卫——更新指引导航并落回工作台（QA2 F-05）。
        if(!state.auth.token){state.cap=null;showLogin();updateGuideNav();return;}
        if(!cap.upload_limits){handleSessionExpired();return;}
        if(!state.auth.user){try{await loadMe();}catch(e){if(!current(t))return;if(e.code==='CONNECTION')errorNotice(e);return;}if(!current(t))return;}
      }
      hideLogin();renderAuthUI();state.cap=cap;renderFooter();
      if(!state.importMode)state.importMode='revision';
      // FL-D1060（用户原话）：后端已支持 .doc 自动转换——文案与前端通路照开。
      $('upload-limit').textContent=`支持 DOCX / .doc（.doc 上传后将自动转换） · 单文件 ≤ ${size(cap.upload_limits.max_file_bytes)}`;
      renderImport();if(state.view==='feishu'){loadFeishuBinding();loadFeishuApp();}if(state.view==='models')loadModelSettings();
      if(!wasReady&&state.view==='overview')restoreRevisionFilters();
      if(!wasReady)dispatchRoute();
      if(state.view==='document'&&!state.detail)openDocumentRoute(state.route);
      if(state.view==='task'&&!state.taskGuides)loadTaskGuides(true);
      if(state.view==='task'&&state.route?.id&&state.selected!==state.route.id)selectTask(state.route.id,false);
    }catch(e){if(current(t)){if(!wasReady)state.cap=null;errorNotice(e);}}
  }
  document.addEventListener('click',e=>{
    const action=e.target.closest('[data-action]')?.dataset.action;
    if(!['feishu-binding-refresh','feishu-unbind','feishu-unbind-confirm','feishu-unbind-cancel','feishu-app-open','feishu-app-close','feishu-app-to-credentials','feishu-app-copy-scopes','feishu-app-recheck','feishu-app-copy-code','feishu-app-new-code','feishu-app-remove','feishu-app-view-config','feishu-app-back-test','feishu-app-reenter','feishu-app-back'].includes(action))return;
    e.stopImmediatePropagation();
    if(action==='feishu-binding-refresh')loadFeishuBinding();
    if(action==='feishu-unbind'){$('feishu-unbind-confirm').hidden=false;document.querySelector('[data-action="feishu-unbind-confirm"]').focus();}
    if(action==='feishu-unbind-cancel'){$('feishu-unbind-confirm').hidden=true;$('feishu-unbind-btn').focus();}
    if(action==='feishu-unbind-confirm')revokeFeishuBinding();
    if(action==='feishu-app-open')openFeishuAppWizard();
    if(action==='feishu-app-close')closeFeishuAppWizard();
    if(action==='feishu-app-to-credentials'){feishuApp.localStep=2;feishuAppRenderPanel(feishuApp.data||{configured:false});$('feishu-app-id').focus();}
    if(action==='feishu-app-copy-scopes')copyText((feishuApp.data?.guide?.required_scopes||[]).map(s=>s.key).join('\n'),'权限清单已复制，去飞书「权限管理」逐个粘贴。');
    if(action==='feishu-app-recheck')feishuAppRecheck();
    if(action==='feishu-app-copy-code')copyText(feishuApp.code||'','绑定码已复制。');
    if(action==='feishu-app-new-code')feishuAppNewCode();
    if(action==='feishu-app-view-config'){feishuApp.localPanel=3;feishuAppRenderPanel(feishuApp.data||{configured:false});}
    if(action==='feishu-app-back-test'){feishuApp.localPanel=null;feishuAppRenderPanel(feishuApp.data||{configured:false});}
    if(action==='feishu-app-reenter'){feishuApp.reenterFrom=feishuAppStep(feishuApp.data||{configured:false});feishuApp.localPanel=2;feishuAppRenderPanel(feishuApp.data||{configured:false});$('feishu-app-id').value=(feishuApp.data&&feishuApp.data.app_id)||'';$('feishu-app-secret').value='';$('feishu-app-secret').focus();}
    if(action==='feishu-app-back'){feishuApp.localPanel=feishuApp.reenterFrom||null;feishuApp.reenterFrom=null;feishuAppRenderPanel(feishuApp.data||{configured:false});}
    if(action==='feishu-app-remove')feishuAppRemove();
  });
  document.addEventListener('submit',e=>{if(e.target&&e.target.id==='feishu-app-form')feishuAppSubmit(e);});
  // FL-D1120补锚6：后端 exceptions 字段含 incomplete；「无报错=完成」语义下
  // 异常徽标/进度红闸一律按 失败+接收失败 计（不再采纳旧 exceptions 字段，避免漏改语义蔓延）。
  function taskMetrics(t){const failed=t.failed||0,rejected=t.rejected||0,dc=t.delivery_counts||{};return {success:(dc.complete||0)+(dc.complete_with_exceptions||0)+(dc.incomplete||0),anomaly:failed+rejected,breakdown:`失败 ${failed} · 接收失败 ${rejected}`};}
  function taskRow(t){const m=taskMetrics(t),pct=t.total?Math.round(100*(t.completed||0)/t.total):0;return `<tr data-row-key="${esc(t.id)}"><td><span class="filename task-list-name" title="${esc(t.name)}">${esc(t.name)}</span></td><td><strong>${t.total}</strong></td><td title="${esc(m.breakdown)}"><span class="task-success">${m.success}</span> / <span class="task-error">${m.anomaly}</span></td><td>${badge(t.status)}</td><td><div class="task-progress"><div class="progress-line mini">${progressHTML(t)}</div><small>${pct}% · ${t.completed}/${t.total} 份终态</small></div></td><td class="task-created-time">${esc(new Date(t.created_at).toLocaleString('zh-CN'))}</td><td><button class="btn-link" data-task="${esc(t.id)}">查看</button></td></tr>`;}
  async function loadTasks(quiet=false) {
    saveRevisionFilters();const t=ticket('tasks'),rows=$('task-rows'),hadData=state.tasksLoaded&&!state.tasksFailed;
    renderFilterChips('task');if(!quiet||!hadData)rows.setAttribute('aria-busy','true');
    try{
      const p=await json(`/api/tasks?${param({q:$('task-search').value.trim(),status:$('task-filter').value,guide_version_id:$('task-guide-filter').value,sort:$('task-sort').value,page:state.taskPage,page_size:state.taskSize})}`);
      if(!current(t))return;state.tasks=p.items;state.taskPage=p.page;state.tasksLoaded=true;state.tasksFailed=false;
      renderTaskGuideFilter();renderTaskRows();syncFirstRunGuide();renderFilterChips('task');patchHTML($('task-pagination'),pagination('task',p.total,p.page,p.page_size));refreshNote('task');renderTask();
      if(!state.selected&&p.items.length)await selectTask(p.items[0].id,false);
    }catch(e){if(current(t)){
      if(!hadData){state.tasksLoaded=true;state.tasksFailed=true;patchHTML(rows,emptyRow(7,'任务暂未加载，请检查连接后刷新'));}
      else refreshNote('task',true);
      if(!quiet||!hadData)errorNotice(e);renderTask();
    }}finally{if(current(t))rows.removeAttribute('aria-busy');}
  }
  async function selectTask(id,navigate=true) {if(!id)return;state.tasksFailed=false;const t=ticket('selection');state.selected=id;state.task=null;state.docPage=1;state.taskDocs=[];state.review=null;state.reviewDecisions=new Map();state.reviewDocs=null;state.reviewDocsTask=null;state.reviewDocsKey='';$('doc-pagination').replaceChildren();$('doc-reason-filter').innerHTML='<option value="">全部原因</option>';window.FundLexSelectKit?.feed($('doc-reason-filter'));closeDetail();state.tokens.doc=(state.tokens.doc || 0)+1;$('doc-rows').innerHTML=emptyRow(7,'正在加载任务');renderTask();try{const task=await json(pathTask(id));if(!current(t)||state.selected!==id)return;state.task=task;renderBreadcrumb();renderTask();if(navigate)go('task');else if(state.view==='task')loadDocuments();}catch(e){if(current(t))errorNotice(e);}}
    function docReason(d) {if(isDirectDoc(d))return directDocNote(d);if(d.upload_status==='rejected')return reason(d.error_code)||'接收校验未通过，请检查源文件后补传';if(d.upload_status==='pending')return '尚未上传，请选择本地文件补传';if(d.eligibility==='excluded_by_fund_type')return '基金类型不在本流程范围，已整份排除';if(d.error_code)return reason(d.error_code);if(d.reason_codes?.length)return reason(d.reason_codes[0]);if(displayJobStatus(d)==='paused')return '任务已暂停，恢复任务后将继续处理';if(['running','leased'].includes(d.job_status))return '正在处理，尚无结论';if(d.job_status==='queued')return '排队等待处理';if(d.job_status==='retry_wait')return '暂时异常，等待自动重试';if(d.delivery_status==='diagnosed')return '只读诊断已完成，仅提供诊断报告，未交付修改后的合同';if(d.delivery_status==='evaluation_modified')return '合同修订（评测）已完成，可下载评测修改版核对';if(d.delivery_status==='evaluation_modified_with_exceptions')return '合同修订（评测）已经完成；有条款未自动修改，按例外清单人工核对后使用';if(d.delivery_status==='evaluation_unmodified')return '原合同已符合当前规则，无需修改';if(d.delivery_status==='complete_with_exceptions')return '合同已修订并校验通过；有条款未自动修改，按例外清单人工核对后使用';if(d.delivery_status==='incomplete')return '部分条款未按规则自动修改位置，已生成修订版和工作文件供核对；请在「还要人工核」中按章节和原文检查（修订版不会标出未修改位置）';if(d.delivery_status==='complete')return '合同已修改完成，可查看报告并下载';if(d.job_status==='succeeded')return '处理已结束，未生成可交付合同文件';return '尚未生成修改后的合同';}
  function targetChip(doc) {if(!doc||isDirectDoc(doc))return '';const counts=doc.target_counts;if(!counts||!Number.isFinite(counts.total))return '';return `<span class="chip-target" title="目标条款完成情况">目标 ${counts.total} · 已完成 ${counts.completed || 0} · 未完成 ${counts.unresolved || 0}</span>`;}
  function docRowClass(d){const clean=d.job_status==='succeeded'&&d.delivery_status==='complete'&&d.eligibility==='eligible';if(d.job_status==='failed'||d.upload_status==='rejected'||d.eligibility==='failed'||(d.job_status==='succeeded'&&d.delivery_status==='not_generated'&&d.eligibility!=='excluded_by_fund_type'))return 'row-exception';return clean?'row-muted':'';}
  function syncDocColumns(direct){const q=$('doc-col-qualification'),d=$('doc-col-delivery'),j=$('doc-col-job');if(q)q.textContent=direct?'处理结果':'资格';if(d)d.textContent=direct?'修改处数':'交付完整性';if(j)j.textContent='处理状态';for(const id of ['doc-qualification-filter','doc-completeness-filter']){const el=$(id);if(!el)continue;el.hidden=!!direct;if(direct)el.value='';}}
  async function loadDocuments(quiet=false) {
    const name='doc',cols=7,id=state.selected,t=ticket('doc'),rows=$('doc-rows'),binding=`${state.epoch}:${id}`,hadData=rows.dataset.loadedFor===binding;
    renderFilterChips('doc');if(!id){patchHTML(rows,emptyRow(cols,'从任务总览选择任务'));return;}
    const values={q:$('doc-search').value.trim(),upload_status:$('doc-upload-filter').value,eligibility:$('doc-qualification-filter').value,job_status:$('doc-status-filter').value,delivery_status:$('doc-completeness-filter').value,error_code:$('doc-reason-filter').value,sort:$('doc-sort').value,page:state.docPage,page_size:state.docSize};
    if(!quiet||!hadData)rows.setAttribute('aria-busy','true');
    try{
      const p=await json(`${pathTask(id)}/documents?${param(values)}`);if(!current(t)||state.selected!==id)return;
      state.taskDocs=p.items;state.docPage=p.page;
      syncDocColumns(state.task?.result_schema==='direct_edit_v1'||p.items.some(isDirectDoc));
      patchHTML(rows,p.items.map((d,i)=>{
        if(isDirectDoc(d)){const outcome=directOutcome(null,d),count=Number.isInteger(d.edit_count)?d.edit_count:null;
          const retryBtn=`<button class="btn-link" data-doc-retry="${esc(d.document_id)}" ${directRetryable(d)?'':'disabled'} title="${directRetryable(d)?'重新提交该合同处理':'当前状态不能重试（处理中/已成功/已达重试上限）'}">重试</button>`;
          return `<tr data-row-key="${esc(d.document_id||d.client_id||i)}" class="${outcome==='failed'?'row-exception':''}"><td><span class="filename" title="${esc(d.name)}">${esc(d.name)}</span></td><td>${badge(d.upload_status,d.upload_status==='pending'?'待上传':null)}</td><td><strong>${esc(DIRECT_OUTCOME_TEXT[outcome]||'处理完成')}</strong></td><td>${outcome==='complete'||outcome==='incomplete'?(count===null?'—':`修改 ${count} 处`):'—'}</td><td>${badge(displayJobStatus(d))}</td><td class="reason-cell">${esc(directDocNote(d))}</td><td><button class="btn-link" data-detail="${name}:${i}">查看结果</button>${outcome==='failed'?retryBtn:''}</td></tr>`;}
        return `<tr data-row-key="${esc(d.document_id||d.client_id||i)}" class="${docRowClass(d)}"><td><span class="filename" title="${esc(d.name)}">${esc(d.name)}</span>${targetChip(d)}</td><td>${badge(d.upload_status,d.upload_status==='pending'?'待上传':null)}</td><td>${badge(d.eligibility || 'pending')}</td><td>${badge(d.delivery_status)}</td><td>${badge(displayJobStatus(d))}</td><td class="reason-cell">${esc(docReason(d))}</td><td><button class="btn-link" data-detail="${name}:${i}">查看结果</button></td></tr>`;}).join('')||emptyRow(cols,'当前筛选下没有匹配的合同，可调整搜索或筛选条件'));
      rows.dataset.loadedFor=binding;patchHTML($('doc-pagination'),pagination(name,p.total,p.page,p.page_size));refreshNote('doc');
      const selected=$('doc-reason-filter').value,options=p.reason_options || [];
      patchHTML($('doc-reason-filter'),'<option value="">全部原因</option>'+options.map(o=>`<option value="${esc(o.code)}">${esc(reason(o.code))}（${o.count}）</option>`).join('')+(selected&&!options.some(o=>o.code===selected)?`<option value="${esc(selected)}">${esc(reason(selected))}</option>`:''));
      $('doc-reason-filter').value=selected;
    }catch(e){if(current(t)&&state.selected===id){
      if(!hadData)patchHTML(rows,emptyRow(cols,'合同列表暂未加载，请刷新'));else refreshNote('doc',true);
      if(!quiet||!hadData)errorNotice(e);
    }}finally{if(current(t))rows.removeAttribute('aria-busy');}
  }
  // 任务暂停时，未进入终态的合同不再显示“排队中/处理中”，避免误以为仍在推进。
  function displayJobStatus(d){return state.task?.status==='paused'&&['queued','running','leased','retry_wait','not_started'].includes(d?.job_status)?'paused':d?.job_status;}
  async function openDeepLinkedTask(){const params=new URLSearchParams(location.search),id=params.get('task');if(!id)return;if(state.auth.mode==='password'&&!state.auth.token)return;const clear=()=>{params.delete('task');const query=params.toString();history.replaceState(null,'',location.pathname+(query?'?'+query:'')+location.hash);};try{await json(pathTask(id));}catch(e){if(e.name==='AbortError'||e.code===401)return;if(e.code===404||e.code===403){clear();go('overview');toast('链接中的任务不存在，或不属于当前登录账号。已返回任务总览，请确认账号或让任务所有者重新分享。',true);return;}toast('链接中的任务暂未打开，请检查网络后重试。',true);return;}await selectTask(id);clear();}
   async function refresh(quiet=false) {const id=state.selected,selectionToken=state.tokens.selection,t=ticket('refresh');await loadCapabilities();if(!current(t))return;if(state.auth.mode==='password'&&!state.auth.token)return;await loadTasks(quiet);if(!current(t))return;if(id&&state.selected===id&&selectionToken===state.tokens.selection)try{const previous=state.task?.status;const task=await json(pathTask(id));if(!current(t)||state.selected!==id||selectionToken!==state.tokens.selection)return;state.task=task;renderTask();if(previous&&previous!==task.status&&['completed','completed_with_exceptions','failed'].includes(task.status)&&['uploading','queued','running','paused'].includes(previous)){notify(`${task.name}：${task.status==='failed'?'处理失败':task.status==='completed_with_exceptions'?'处理结束（含异常）':'处理结束'}，请查看结果`,false,task.id);if(document.visibilityState==='hidden')document.title=`✓ ${task.name} 处理结束 · FundLex`;}}catch(e){if(current(t))errorNotice(e);}if(current(t)&&state.view==='task')await loadDocuments(quiet);if(current(t))syncFirstRunGuide();if(current(t)&&state.view==='overview'&&(!quiet||!state.taskGuides))await loadTaskGuides(quiet);if(current(t)&&state.view==='guide'&&!state.guideBusy)await loadGuides(true);}
  function importAnalysis() {const seen=new Set();const checked=state.imports.map(f=>{let issue='';const key=f.name.toLowerCase()+'|'+f.size;if(!/\.docx?$/i.test(f.name))issue='不支持格式：仅接收 DOCX / .doc';else if(!f.size)issue='空文件，无法接收';else if(state.cap&&f.size>state.cap.upload_limits.max_file_bytes)issue=`超过单文件 ${size(state.cap.upload_limits.max_file_bytes)} 限制`;else if(seen.has(key))issue='疑似重复：文件名与大小相同';else if(state.recover&&!f.client_id)issue='与待补传清单不匹配';else seen.add(key);return {...f,issue:issue||f.serverIssue||''};});return {checked,accepted:checked.filter(f=>!f.issue),issues:checked.filter(f=>!!f.issue).length,total:checked.reduce((s,f)=>s+f.size,0)};}
  function nameError(show) {const value=$('task-name').value.trim(),bad=show&&!value,field=$('task-name-error');field.hidden=!bad;$('task-name').setAttribute('aria-invalid',bad?'true':'false');$('task-name').classList.toggle('invalid',bad);return !bad;}
  function syncImportMode() {const select=$('import-mode'),note=$('import-mode-note');if(!select)return;select.value='revision';select.disabled=true;if(!note)return;if(state.recover){note.textContent='补传沿用原任务的处理模式，不能切换。';return;}note.textContent=guideReady()?'使用当前指引修订合同，产出修订痕迹与最终版；可逐条审查接受或拒绝。':'当前指引不可用，暂时不能创建任务；请先在「指引配置」启用可用指引。';}
  function renderImport() {$('export-pending').hidden=!state.recover;$('cancel-recover').hidden=!state.recover;syncImportMode();renderGuideBinding();renderFilterChips('import');renderUploadProgress();const a=importAnalysis(),q=$('import-search').value.trim().toLowerCase(),filter=$('import-filter').value,matching=a.checked.filter(f=>f.name.toLowerCase().includes(q)&&(!filter||(filter==='accepted'?!f.issue:!!f.issue))),pages=Math.max(1,Math.ceil(matching.length/state.importSize));state.importPage=Math.min(state.importPage,pages);const shown=matching.slice((state.importPage-1)*state.importSize,state.importPage*state.importSize);$('import-stats').innerHTML=[['文件总数',state.imports.length],['总大小',size(a.total)],['可接收',a.accepted.length],['异常',a.issues]].map(([l,n])=>`<span class="inline-kpi"><b>${n}</b>${l}</span>`).join('');$('import-validation').textContent=state.recover?`补传模式：待补传 ${state.recover.manifest.length} 份 · 已匹配 ${state.imports.filter(f=>f.client_id).length} 份。`:'异常文件不会提交，请检查重复文件。';$('import-rows').innerHTML=shown.map(f=>{const cls=f.issue?'row-exception':f.received?'row-muted':'';const statusLabel=f.issue||(f.received?'已接收':state.uploading?'上传中':'可接收');return `<tr class="${cls}"><td><span class="filename" title="${esc(f.name)}">${esc(f.name)}</span></td><td>${size(f.size)}</td><td>${badge(f.issue?'rejected':f.received?'accepted':state.uploading?'running':'accepted',statusLabel)}</td><td><div class="row-actions"><button class="btn-link" data-replace="${esc(f.id)}" ${state.uploading?'disabled':''} aria-label="替换 ${esc(f.name)}">替换</button><button class="btn-link" data-remove="${esc(f.id)}" ${state.uploading?'disabled':''} aria-label="移除 ${esc(f.name)}">移除</button></div></td></tr>`;}).join('');$('import-empty').hidden=matching.length>0;$('import-empty').innerHTML='<strong>当前清单没有匹配文件</strong>选择多个 DOCX / .doc、文件夹，或调整筛选。';$('import-pagination').innerHTML=pagination('import',matching.length,state.importPage,state.importSize);$('task-check').innerHTML=[['任务文件',`${state.recover?.total ?? state.imports.length} 份`],['本次可接收',`${a.accepted.length} 份`],['待确认异常',`${a.issues} 份`],['可接收总大小',size(a.accepted.reduce((n,f)=>n+f.size,0))]].map(([l,n])=>`<div class="plan-row"><strong>${l}</strong><span>${n}</span></div>`).join('');$('submit-task').disabled=!a.accepted.length||state.uploading||!state.cap||(!state.recover&&!guideReady());$('submit-task').textContent=state.uploading?'正在上传…':state.recover?'补传到原任务':'创建任务并上传';$('task-name').disabled=!!state.recover;document.querySelectorAll('[data-action="choose-files"],[data-action="choose-folder"],[data-action="clear-import"]').forEach(n=>n.disabled=state.uploading);}
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
      for(const f of sessionFiles){if(group.length&&(bytes+f.size>limits.max_request_bytes)){groups.push(group);group=[];bytes=0;}group.push(f);bytes+=f.size;}
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
  async function togglePause() {const id=state.selected,task=state.task;if(!task||['completed','completed_with_exceptions','failed'].includes(task.status))return;const t=ticket('control');$('pause-btn').disabled=true;try{const p=await json(`${pathTask(id)}/${task.status==='paused'?'resume':'pause'}`,{method:'POST'});if(!current(t)||state.selected!==id)return;state.task=p;renderTask();await loadDocuments();if(current(t)&&state.selected===id)flash(['completed','completed_with_exceptions','failed'].includes(p.status)?'任务已处理结束，结果可查看。':p.status==='paused'?'整个任务已暂停，正在执行的合同可安全结束。':'任务已继续。');}catch(e){if(current(t))errorNotice(e);}finally{if(current(t)&&state.selected===id)renderTask();}}
  async function download(url,filename) {const t=ticket('download');try{const {response,epoch}=await api(url);const blob=await response.blob();if(!current(t)||!identityCurrent(epoch))return;const disposition=response.headers.get('Content-Disposition')||'';const encoded=disposition.match(/filename\*=UTF-8''([^;]+)/i),plain=disposition.match(/filename="([^"]+)"/i);if(encoded){try{filename=decodeURIComponent(encoded[1]);}catch{}}else if(plain)filename=plain[1];const object=URL.createObjectURL(blob),a=document.createElement('a');a.href=object;a.download=filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(object),1000);}catch(e){if(current(t))errorNotice(e,'下载失败：');}}
  function csvEscape(value){const s=String(value??'');return /[",\n\r]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s;}
  function downloadText(text,filename,mime='text/csv;charset=utf-8'){const blob=new Blob([text],{type:mime});const object=URL.createObjectURL(blob),a=document.createElement('a');a.href=object;a.download=filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(object),1000);}
  async function exportResults(){const id=state.selected;if(!id)return;const button=document.querySelector('[data-action="export-results"]');if(button)button.disabled=true;const t=ticket('export');try{const values={q:$('doc-search').value.trim(),upload_status:$('doc-upload-filter').value,eligibility:$('doc-qualification-filter').value,job_status:$('doc-status-filter').value,delivery_status:$('doc-completeness-filter').value,error_code:$('doc-reason-filter').value,sort:$('doc-sort').value,page_size:200,page:1};let all=[],total=Infinity,page=1;while(all.length<total&&page<=100){const p=await json(`${pathTask(id)}/documents?${param({...values,page})}`);if(!current(t)||state.selected!==id)return;all.push(...p.items);total=p.total;if(!p.items.length)break;page++;}const direct=all.some(isDirectDoc);
      const rows=direct
        ?[['序号','文件名','处理结果','修改处数','可下载文件']].concat(all.map((d,i)=>{const o=directOutcome(null,d);const dl=d.downloads||{};const files=[dl.final?'最终版':'',dl.redline?'带痕版':'',dl.selected_final?'选择版':''].filter(Boolean).join('、')||'—';return [i+1,d.name,DIRECT_OUTCOME_TEXT[o]||'处理完成',o==='complete'||o==='incomplete'?(Number.isInteger(d.edit_count)?d.edit_count:'—'):'—',o==='complete'?files:'—'];}))
        :[['序号','文件名','资格','处理状态','交付完整性','业务提示','原始原因码']].concat(all.map((d,i)=>[i+1,d.name,labels[d.eligibility||'pending']||'未判定',labels[d.job_status]||d.job_status,labels[d.delivery_status]||d.delivery_status,docReason(d),(d.reason_codes||[]).join('；')||d.error_code||'']));const csv='\ufeff'+rows.map(r=>r.map(csvEscape).join(',')).join('\r\n');downloadText(csv,`${state.task?.name||'任务'}_结果清单.csv`);toast(`已导出 ${all.length} 条状态清单（仅状态，不含合同文件）`);}catch(e){if(current(t))errorNotice(e,'导出失败：');}finally{if(button)button.disabled=false;}}
  function exportPending(){const recovering=state.recover;if(!recovering)return;const rows=[['文件名','大小(字节)','状态']].concat(recovering.manifest.map(d=>[d.name,d.size,d.upload_status==='rejected'?'接收失败':'待上传']));const csv='\ufeff'+rows.map(r=>r.map(csvEscape).join(',')).join('\r\n');downloadText(csv,`${recovering.name||state.task?.name||'任务'}_待补传清单.csv`);toast(`已导出待补传清单 ${recovering.manifest.length} 条`);}
  const proof = item => {if(typeof item==='string')return item?quoteBox('合同原文引用',item):'';if(!item||typeof item!=='object')return '';const text=item.quote || item.text || item.original_text || '';if(!text)return '';return quoteBox('合同原文引用',text);};
  const quoteBox = (label,text,cls='') => `<div class="evidence quote${cls?' '+cls:''}" title="点击展开或收起"><small class="quote-label">${esc(label)}</small><span class="quote-text">${esc(text)}</span></div>`;
  // ── direct_edit_v1 直通报告（新口径，同 fundlex/direct_report.py）───────────
  // 唯一计数来源：写回器重开验证的 changes(status=='written')。plan/提案/target
  // 计数在此口径下绝不展示。旧引擎历史报告继续走后面的 legacy 渲染分支。
  const DIRECT_WRITE_SCHEMA='direct_edit_write_v1';
  function directWriteResult(report){if(!report||typeof report!=='object')return null;if(report.schema_version===DIRECT_WRITE_SCHEMA)return report;for(const key of ['write_result','direct_edit','direct_edit_v1','direct_write']){const c=report[key];if(c&&typeof c==='object'&&(c.schema_version===DIRECT_WRITE_SCHEMA||Array.isArray(c.changes)||('actual_written_count' in c&&'status' in c)))return c;}return null;}
  function isDirectReport(report){return report?.report_contract==='direct_edit_v1'||!!directWriteResult(report)||report?.schema_version==='direct_edit_v1';}
  function isDirectDoc(doc){return !!doc&&(doc.result_schema==='direct_edit_v1'||doc.report_schema==='direct_edit_v1');}
  const DIRECT_ACTION={replace:'替换',delete:'删除',insert_before:'新增（条款前）',insert_after:'新增（条款后）',insert:'新增'};
  function directChanges(report){const w=directWriteResult(report);if(!w)return [];const cards=new Map(((report&&report.guide&&report.guide.cards)||[]).map(c=>[String(c.card_id),String(c.title||c.card_id)]));const rows=[];for(const item of w.changes||[]){if(!item||item.status!=='written')continue;const cardId=String(item.rule_card_id||'');rows.push({action:DIRECT_ACTION[item.action]||'修改',location:String(item.section_path||item.location||'—'),before:String(item.before||'').trim(),after:String(item.after||'').trim(),card:cardId,cardTitle:cards.get(cardId)||cardId||'—'});}return rows;}
  function directCount(report,doc){const rows=directChanges(report);if(rows.length)return rows.length;const w=directWriteResult(report);if(w&&w.changes==null&&Number.isInteger(w.actual_written_count)&&w.actual_written_count>0)return w.actual_written_count;if(!report&&doc&&Number.isInteger(doc.edit_count))return doc.edit_count;return rows.length;}
  function directOutcome(report,doc){doc=doc||{};if(doc.upload_status==='rejected')return 'failed';const job=doc.job_status||'';const w=directWriteResult(report);
    // 第 4 线冻结契约：终态权威字段 delivery_status ∈ {complete, incomplete, not_generated}
    const delivery=doc.delivery_status||report?.delivery_status||'';
    if(!w&&!delivery){if(['queued','running','leased','retry_wait','paused','not_started',''].includes(job)&&!doc.outcome)return 'processing';if(job==='failed')return 'failed';if(doc.outcome)return doc.outcome;}
    if(job==='failed')return 'failed';
    if(delivery==='not_generated')return 'failed';
    if(delivery==='complete'||delivery==='incomplete')return delivery;
    return directCount(report,doc)>=1?'complete':'incomplete';}
  const DIRECT_OUTCOME_TEXT={complete:'完成',incomplete:'处理完成',processing:'处理中',failed:'处理失败'};
  function directNote(report,doc){const o=directOutcome(report,doc);if(o==='complete')return `实际修改 ${directCount(report,doc)} 处；「完成」表示本次处理已形成可交付修改并提供下载，不代表合同所有条款均已复核完毕。`;if(o==='processing')return '合同仍在处理中，结束后会显示实际修改结果。';if(o==='failed')return '本次处理发生故障，没有形成可交付的修改；可重新上传该合同再试一次。';return '本次按指引核对后没有形成可交付的修改，合同未做改动。';}
  // 附带项①：失败行把错误 entries 的第一行错误码+脱敏堆尾捎进 reason（路径不外露）
  function directFailureDigest(doc){const entries=Array.isArray(doc.errors)?doc.errors:[];
    const first=entries.find(e=>e&&(e.code||e.message||e.detail));
    let code=first&&(first.code||'')||doc.error_code||'';
    if(!code)return '';
    let tail='';
    if(first){const src=String(first.detail||first.message||'').trim().split('\n').filter(Boolean);
      const last=(src[src.length-1]||'').replace(/[\w/.-]*\/([\w.-]+)/g,'$1').slice(0,90).trim();
      if(last&&last!==code)tail=last;}
    return tail?`（${code}：${tail}）`:`（${code}）`;}
  function directDocNote(doc){const o=directOutcome(null,doc);if(['queued','running','leased'].includes(doc.job_status)&&!doc.delivery_status)return '正在处理，尚无结论';if(doc.job_status==='queued')return '排队等待处理';if(displayJobStatus(doc)==='paused'&&!doc.delivery_status)return '任务已暂停，恢复任务后将继续处理';if(o==='failed')return `处理发生故障，未生成可交付文件${directFailureDigest(doc)}；可重新上传该合同再试`;if(o==='complete')return `已实际修改 ${doc.edit_count??'?'} 处，可查看逐处对照并下载`;return '本次没有形成可交付的修改，合同未做改动';}
  function directRetryable(d){return d.job_status==='failed'&&(Number(d.attempt??d.attempts??0)<3);}
  // 附带项②：手动重试——202→该行回排队态；409→按当前状态给诚实文案
  async function retryFailedDocument(documentId,button){const taskId=state.selected;if(!taskId||!documentId)return;
    const t=ticket('doc-retry');
    try{const response=await fetch(`${pathTask(taskId)}/documents/${encodeURIComponent(documentId)}/retry`,{method:'POST',cache:'no-store'});if(!current(t)||state.selected!==taskId)return;
      if(response.status===202){toast('已重新排队，将在 Worker 空闲时重试该合同。');const doc=state.taskDocs.find(d=>d.document_id===documentId);if(doc){doc.job_status='queued';delete doc.delivery_status;}
        if(button){button.disabled=true;button.textContent='已排队';}
        await loadDocuments(true);return;}
      if(response.status===409){let detail='';try{detail=(await response.json()).detail||'';}catch{}
        toast(detail==='LEGACY_READ_ONLY'?'该合同来自历史任务，不支持重试。':'当前状态不能重试：处理中的合同无需重试，已成功的无需重试，已达重试上限的请重新上传。',true);return;}
      if(response.status===401){handleSessionExpired();return;}
      throw new Error(`重试失败（${response.status}）`);}
    catch(e){if(current(t)&&e.name!=='AbortError')errorNotice(e,'重试未完成：');}}
  const DIRECT_FINAL_NOTE='最终版为全部修订已定案的版本：其中既有本次按指引的修改，也包括合同中原有的修订痕迹，均已定案不再显示标记。带痕版保留全部修订标记，可在 Word 中逐条接受或拒绝。';
  // 拍板 C：normalized_base 档显著标注；tracked_overlay 档不标注
  const NORMALIZED_BASE_NOTE='本合同原修订痕迹已并入定稿，无法单独撤回原修订。';
  function directTier(report,doc){for(const src of [report,report&&report.direct_edit,directWriteResult(report),doc]){if(src&&src.revision_tier)return String(src.revision_tier);}const w=directWriteResult(report);if(w&&w.write_result&&w.write_result.revision_tier)return String(w.write_result.revision_tier);return 'strict_dual_layer';}
  function directTierNote(report,doc){return directTier(report,doc)==='normalized_base'?NORMALIZED_BASE_NOTE:'';}
  function directDownloadButton(kind){const labels={final:'最终版（全部修订已定案）',redline:'带痕版（保留全部修订标记）',selected_final:'选择版（按您的接受/拒绝）',selected_redline:'选择版（带痕）'};return `<button class="btn ${kind==='final'?'btn-primary':''} btn-sm" data-download="${kind}">${labels[kind]||kind}</button>`;}
  function renderDirectReport(doc,report){
    const outcome=directOutcome(report,doc),count=directCount(report,doc),changes=directChanges(report);
    const headline=outcome==='complete'?`完成 · 实际修改 ${count} 处`:outcome==='processing'?'处理中':outcome==='failed'?'处理失败':'未完成';
    const tierNote=directTierNote(report,doc);
    let html=`<section class="result-summary" aria-label="结论"><div class="result-verdict"><h2>结论</h2><strong>${headline}</strong></div><p class="result-reason">${esc(directNote(report,doc))}</p>${tierNote?`<p class="result-warning" role="note">${esc(tierNote)}</p>`:''}<dl class="result-status-grid"><div><dt>处理结果</dt><dd>${esc(DIRECT_OUTCOME_TEXT[outcome]||'处理完成')}</dd></div></dl>${(report?.has_toc_field===true||directWriteResult(report)?.has_toc_field===true)?'<p class="result-warning">下载后请在 Word 中更新目录。</p>':''}</section>`;
    const downloads=doc.downloads||{};
    const kinds=outcome==='complete'?['final','redline','selected_final','selected_redline']:['redline','selected_redline'];
    const buttons=kinds.filter(kind=>downloads[kind]).map(directDownloadButton).join('');
    html+=`<div class="result-action-grid">${buttons?`<section class="detail-section result-files"><h3>下载区</h3><div class="detail-actions">${buttons}</div><p class="subnote">${esc(DIRECT_FINAL_NOTE)}</p></section>`:''}${report&&outcome==='complete'?revisionSection(doc,report):''}</div>`;
    if(report&&outcome==='complete'&&tierNote)html+=`<p class="subnote">修订审查的「改动清单」=本次按指引的修改（我方修订）；原文件的修订已并入正文，其修改人可在「修改人」筛选里查看；${esc(tierNote)}</p>`;
    if(changes.length){
      html+=`<section class="detail-section"><h3>改了哪些条款 · ${changes.length} 处</h3>${changes.map((c,i)=>`<details class="action-evidence"><summary><span class="clause-section">${i+1}. ${esc(c.location)}</span> <span class="badge b-blue">${esc(c.action)}</span> <span class="chip">${esc(c.cardTitle)}</span></summary><div class="clause-compare">${c.before?quoteBox('改之前',c.before,'quote-before'):''}${quoteBox('改成了什么',c.after||'（删除该句）','quote-after')}</div></details>`).join('')}</section>`;
    }else if(outcome==='processing'){
      html+='<p class="result-pending">报告尚未生成，处理完成后可查看。</p>';
    }
    $('detail-body').innerHTML=html;
  }
  // 业务可读的条款改动：章节名 + 状态 + 改之前/改成了什么（不展示位置、字符偏移、哈希等技术字段）。
  // 以下 legacy 渲染仅服务历史旧引擎报告（只读兼容），新直通报告走上面的 renderDirectReport。
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
  function resultCounts(report,doc){const tc=(doc&&doc.target_counts)||{};const targets=Array.isArray(report?.targets)?report.targets:[];const DONE=['modified_verified','planned','satisfied','not_applicable','superseded'],UNRES=['unresolved','unsupported','needs_edit'];const total=tc.total??targets.length;const completed=tc.completed??targets.filter(i=>i&&(DONE.includes(i.status||i.state)||i.out_of_scope)).length;const unresolved=tc.unresolved??targets.filter(i=>i&&!i.out_of_scope&&UNRES.includes(i.status||i.state)).length;return {total,completed,unresolved};}
  function unresolvedIssuesHTML(report, summary) {
    const issues=Array.isArray(summary?.issues)?summary.issues:[];
    const exceptions=Array.isArray(report?.exceptions)?report.exceptions:[];
    const total=issues.length+exceptions.length;
    if(!total)return '';
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
      const note=item.review_note||'该规则未写入修订版，修订痕迹中不会出现本处；请在 Word 中搜索下方原文核对。';
      return `<div class="candidate manual-review-item">
        <div class="issue-head"><strong>${index+1}. ${esc(title)}</strong>${section?` <span class="chip">${esc(section)}</span>`:''}<span class="badge b-amber">需人工核</span></div>
        <p>${esc(reason)}</p>
        ${requirement?`<p class="subnote">指引要求：${esc(requirement)}</p>`:''}
        ${found?quoteBox(found.exact?'合同中对应原文':'同规则参考原文（非本处）',found.text):''}
        <p class="subnote">${esc(note)}</p>

      </div>`;
    }).join('');
    const exceptionCards=exceptions.map((e,index)=>`<div class="candidate manual-review-item"><div class="issue-head"><strong>${issues.length+index+1}. ${esc(e.description || e.title || e.action_id || '条款')}</strong><span class="badge b-amber">需人工核</span></div><p>${esc(reason(e.reason)||'该条款未能自动修改，需要人工核对。')}</p></div>`).join('');
    return `<div class="detail-section result-issues"><h3>还要人工核 · ${total} 处</h3>
      <p>未写入的内容不会显示在修订痕迹中，请逐条确认后再使用。${['complete','complete_with_exceptions'].includes(report.delivery_status)?'':'当前合同仍为未完成的工作文件。'}</p>
      ${cards}${exceptionCards}
      <p class="subnote result-issues-tail">核完上述条款后，按下方「接下来怎么做」操作。</p></div>`;
  }
  // FL-D896 N1 明细区塑形：摘要行露出「改为：」预览（减少点开成本）+ 三态徽标语义化（修改/符合=绿、规划=蓝、待修改=琥珀）。
  function clauseRow(row) {
    const op=row.operation||'';
    const status=row.state;
    const after=row.after && row.after.trim()?row.after:(op==='delete'?'':'');
    const beforeBlock=row.before?quoteBox('改之前',row.before,'quote-before'):'';
    const afterBlock=after?quoteBox(row.state==='planned'?'拟修改为（尚未生成）':'改成了什么',after,'quote-after'):(op==='delete'?quoteBox(row.state==='planned'?'拟修改为（尚未生成）':'改成了什么','（删除该句）','quote-after'):'');
    const compare=(beforeBlock||afterBlock)?`<div class="clause-compare">${beforeBlock}${afterBlock}</div>`:'<p class="subnote">报告未提供修改对照。</p>';
    const reasonText=row.reason?(reasons[row.reason]||'其他调整'):'';
    // b-blue 令牌与琥珀同色（--blue=#8a5b14），已规划用 b-gray 保证三态可区分
    const cls=status==='applied'||status==='satisfied'?'b-green':status==='planned'?'b-gray':'b-amber';
    const badgeText=status==='satisfied'?'已符合':status==='applied'?'已修改':status==='planned'?'已规划':'待修改';
    const core=after?after.replace(/\s+/g,' ').trim():(op==='delete'?'（删除该句）':'');
    const previewText=core?(status==='planned'?'拟改为：':'改为：')+core:'';
    return `<details class="action-evidence"><summary><span class="clause-summary"><span class="clause-section">${esc(row.section||'条款')}</span><span class="badge ${cls}">${badgeText}</span>${previewText?`<span class="clause-preview">${esc(previewText.slice(0,50))}${previewText.length>50?'…':''}</span>`:''}</span></summary>${reasonText?`<p>${esc(reasonText)}</p>`:''}${compare}</details>`;
  }
  function selectedContractLabel(doc){return ['complete','complete_with_exceptions'].includes(doc.delivery_status)?'最终版合同':'工作文件（未完成）';}
  function reviewNavInfo(review){
    const docs=review.docs&&review.docs.length?review.docs:[review.doc];
    const index=Math.max(0,docs.findIndex(d=>d.document_id===review.doc.document_id));
    return {docs,index,total:docs.length,prev:index>0?docs[index-1]:null,next:index<docs.length-1?docs[index+1]:null};
  }
  function reviewDraftKey(doc){return `fundlex-v1-review:${state.auth.user?.id||owner()}:${state.selected}:${doc.document_id}`;}
  function reviewDecisionsSave(){const review=state.review;if(!review||!review.doc)return;state.reviewDecisions.set(review.doc.document_id,{...review.chosen});try{sessionStorage.setItem(reviewDraftKey(review.doc),JSON.stringify({binding:review.draftBinding,chosen:review.chosen}));}catch{}}
  function renderReview(){
    const review=state.review, body=$('detail-body'); if(!review||!body) return;
    const chosen=review.chosen || {};
    const nav=reviewNavInfo(review);
    // FL-D1132 定稿口径（用户令 2026-11-04 ~15:0x）：下拉只老老实实显示修改人名字——
    // 原修改人与 FundLex 平列，无条数标注；选中原修改人时标题行提示其修订已并入正文。
    const revAuthors=[...new Set(review.revisions.map(r=>String(r.author||'').trim()).filter(Boolean))];
    const srcAuthors=[...new Set((review.source_revisions||[]).map(s=>String(s.author||'').trim()).filter(Boolean))];
    const allAuthors=[...new Set([...revAuthors,...srcAuthors])];
    state.reviewAuthorFilter='';
    const authorFilterHtml=allAuthors.length>=1?`<label class="review-author-filter">修改人 <select id="review-author-filter" class="control-select" aria-label="按修改人筛选" data-fl-selectvend="off"><option value="">全部修改人</option>${allAuthors.map(a=>`<option value="${esc(a)}">${esc(a)}</option>`).join('')}</select></label>`:'';
    const items=review.revisions.map(r=>{
      const verdict=chosen[r.del_id] || 'accept';
      const before=r.before && r.before.trim() ? quoteBox('原文',r.before,'quote-before') : '';
      const after=r.after && r.after.trim() ? quoteBox('修改为',r.after,'quote-after') : quoteBox('修改为','（删除该句）','quote-after');
      const ops={insert:'新增',delete:'删除',replace:'替换'};
      return `<li class="rev-item ${verdict==='reject'?'rejected':''} ${String(review.active)===String(r.del_id)?'active':''}" data-rev-item="${r.del_id}" data-rev-author="${esc(r.author||'')}" tabindex="-1">
        <div class="rev-head"><span class="rid">#${r.index}</span>${r.author?`<span class="rev-author" title="修改人">${esc(r.author)}</span>`:''}${r.rule_id?`<span class="rule">规则 ${esc(r.rule_id)}</span>`:''}
          <span class="rev-op">${ops[r.operation]||esc(r.operation||'修改')}</span>
          <label><input type="checkbox" data-rev-toggle="${r.del_id}" ${verdict==='accept'?'checked':''} aria-label="接受第 ${r.index} 条修订"> 接受</label></div>
        ${r.section?`<p class="rev-sec">${esc(r.section)}</p>`:''}
        <div class="clause-compare">${before}${after}</div></li>`;
    }).join('');
    // FL-D1132 定稿口径②（用户令 ~15:1x）：原修改人的修订=可筛选的真实条目——
    // 进主清单但默认隐藏,选中其名字时显示;惰性条目(不可接受/拒绝、不可跳转)。
    const srcItems=(review.source_revisions||[]).map(s=>{
      const before=s.before?quoteBox('原文',s.before,'quote-before'):'';
      const after=s.after?quoteBox('修改为',s.after,'quote-after'):'';
      const ops={insert:'新增',delete:'删除',replace:'替换'};
      return `<li class="rev-item rev-item-source" data-rev-src="1" data-rev-author="${esc(s.author||'')}" hidden>
        <div class="rev-head"><span class="rid">#${s.index}</span>${s.author?`<span class="rev-author" title="修改人">${esc(s.author)}</span>`:''}<span class="rev-op">${ops[s.kind]||'修改'}</span><span class="rule">原文修订（已并入正文）</span></div>
        <div class="clause-compare">${before}${after}</div></li>`;
    }).join('');
    body.innerHTML=`<div class="review-layout">
        <div class="review-doc-wrap">
        <div id="review-section-nav" class="section-nav-wrap" role="navigation" aria-label="章节导航"></div>
        <div class="review-toolbar"><strong>合同呈现</strong>
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
        <div class="review-splitter" id="review-splitter" role="separator" aria-label="调整改动清单宽度" aria-orientation="vertical" aria-valuemin="280" aria-valuemax="680" aria-valuenow="360" tabindex="0" title="拖动调整修订清单宽度，双击恢复默认"></div>
        <aside class="review-list" id="review-rail"><h3><span class="review-list-title">改动清单 · ${review.revisions.length} 条</span> ${authorFilterHtml}<span class="review-kbd">A 接受 · R 拒绝</span><button class="section-collapse-toggle" id="review-rail-collapse" type="button" aria-expanded="true" aria-controls="review-rail" aria-label="折叠或展开改动清单栏" title="折叠改动清单栏" data-title-expand="展开改动清单栏" data-title-collapse="折叠改动清单栏" data-text-expand="«" data-text-collapse="»">»</button></h3>
          <ol class="rev-list">${items||'<li class="subnote">本合同没有可选择的修订。</li>'}${srcItems}</ol></aside>
      </div>
      <div class="review-actions"><button class="btn btn-primary" data-action="generate-selected">生成选择版合同</button>
        <button class="btn" data-action="review-close">返回报告</button>
        <span class="subnote" id="review-message"></span></div>
      <details class="review-hint"><summary>交付说明与快捷键</summary>
        <p class="subnote">拒绝部分修订后，交付包会同时给出「（全量痕迹版）」和只含接受修订的「（选择修订版）」；全部接受则只有「（全量痕迹版）」，与最终版一致。快捷键：A 接受、R 拒绝；切换合同时保留当前勾选。</p></details>`;
    // FL-D557 F8: index the freshly rendered nodes once. syncReview used to
    // run ~3 full-document querySelector(All) lookups per revision on every
    // toggle; with the index each decision is O(1) map gets.
    const nodeMap=new Map();
    ($('review-doc')||body).querySelectorAll('[data-rev]').forEach(n=>{
      const key=n.getAttribute('data-rev');
      if(!nodeMap.has(key))nodeMap.set(key,[]);
      nodeMap.get(key).push(n);
    });
    const itemMap=new Map();
    body.querySelectorAll('[data-rev-item]').forEach(item=>{
      itemMap.set(String(item.getAttribute('data-rev-item')),{item,input:item.querySelector('[data-rev-toggle]')});
    });
    review.index={nodeMap,itemMap};
    // FL-D1046：章节导航（与合同比对共用 FundLexSectionNav）——样式 doc-heading 优先、
    // 「第X条」正则兜底。数据源=已渲染的合同呈现 DOM，零模型。
    if (window.FundLexSectionNav) {
      const navHost = $('review-section-nav'), navRoot = $('review-doc');
      if (navHost && navRoot) {
        body._sectionNav?.destroy?.();
        body._sectionNav = window.FundLexSectionNav.mount({
          host: navHost, root: navRoot, title: '章节',
          pane: () => navRoot,
          // FL-D1059（用户原话）：章节栏可折叠隐藏——与比对视图相互独立键。
          collapse: {
            key: 'fundlex-review-sectionnav-collapsed',
            gridContainer: document.querySelector('.review-layout'),
            stateClass: 'is-sectionnav-collapsed',
          },
        });
        // FL-D1055-回归（用户原话「修订审查的章节栏现在无法拖动宽度」）：
        // ① review-doc-wrap 只有 class 没有 id——$('review-doc-wrap') 恒为 null
        //    导致 attachSplitter 早返 null（无拉手），改 closest 按真实 DOM 取；
        // ② 修好①后挂重暴露泄漏：每次重开审查 innerHTML 重建（navHost 为
        //    新元素），旧实例无 dispose（A9-F04 存活计数线性+1）——入册
        //    avoid：重进先 dispose 旧实例（与 bindReviewSplitter.dispose 同款）。
        state.sectionNavSplitter?.dispose?.();
        navHost._navSplitter = window.FundLexSectionNav.attachSplitter(
          navHost, navHost.closest('.review-doc-wrap') || navHost.parentElement,
          () => navHost,
          { key: 'fundlex-review-sectionnav-width', variable: '--review-sectionnav-width',
            min: 200, max: 420, fallback: 200, ariaLabel: '调整章节导航宽度' });
        state.sectionNavSplitter = navHost._navSplitter?.instance || null;
        body._sectionNav.render(window.FundLexSectionNav.collect(navRoot, { selector: '.doc-heading, p', levels: [1, 2] }));
        body._sectionNav.refresh();
      }
    }
    syncReview();
    bindReviewSplitter();
  }
  function bindReviewSplitter() {
    const layout = document.querySelector('.review-layout'), handle = $('review-splitter');
    if (!layout || !handle || !window.FundLexColumnSplitter) return;
    // FL-D1059（用户原话）：改动清单栏可折叠隐藏——独立 localStorage 键。
    const railBtn = layout.querySelector('#review-rail-collapse');
    if (railBtn && window.FundLexSectionNav) {
      window.FundLexSectionNav.attachCollapse(
        railBtn, layout, 'is-rail-collapsed', 'fundlex-review-rail-collapsed');
    }
    bindReviewSplitter.instance?.dispose?.();
    bindReviewSplitter.instance = window.FundLexColumnSplitter(handle, layout, layout.querySelector('.review-list'), {
      key: 'fundlex-review-list-width',
      variable: '--review-list-width',
      min: 280, max: 680, minOther: 560, fallback: 360,
      side: 'right',
      disabled: () => matchMedia('(max-width: 1000px)').matches,
    });
  }
  function revisionNodes(revision){
    const ids=revision.revision_ids?.length?revision.revision_ids:[revision.del_id,revision.ins_id??Number(revision.del_id)+1];
    const map=state.review?.index?.nodeMap;
    if(map)return ids.flatMap(id=>map.get(String(id))||[]);
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
      const entry=review.index?.itemMap.get(String(r.del_id));
      const item=entry?entry.item:document.querySelector(`[data-rev-item="${r.del_id}"]`);
      if(item){const input=entry?entry.input:item.querySelector('[data-rev-toggle]');if(input)input.checked=verdict==='accept';item.classList.toggle('rejected',verdict==='reject');item.classList.toggle('active',String(review.active)===String(r.del_id));}
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
    // FL-D557 F8: every revision state is class/checkbox driven, so a class
    // sync covers accept-all/reject-all — no full-document innerHTML rebuild.
    reviewDecisionsSave();syncReview();
    toast(verdict==='accept'?`已全部标记接受（${review.revisions.length} 条）`:`已全部标记拒绝（${review.revisions.length} 条）`);
  }
  function focusRevision(delId){
    const review=state.review;if(!review)return;
    review.active=delId;
    const entry=review.revisions.find(r=>String(r.del_id)===String(delId));
    const node=entry?revisionNodes(entry)[0]:null;
    if(node){const pane=$('review-doc'),nr=node.getBoundingClientRect(),pr=pane.getBoundingClientRect();pane.scrollTop+=nr.top+nr.height/2-pr.top-pr.height/2;}
    const item=document.querySelector(`[data-rev-item="${CSS.escape(String(delId))}"]`),list=document.querySelector('.rev-list');
    if(item&&list){const ir=item.getBoundingClientRect(),lr=list.getBoundingClientRect();if(ir.top<lr.top||ir.bottom>lr.bottom)list.scrollTop+=ir.top-lr.top;}
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
    if(state.view==='document'&&state.route?.tab!=='review'){go('document',{id:state.selected,document:doc.document_id,tab:'review'});return;}
    const t=ticket('review');state.review=null;
    const body=$('detail-body');
    body.innerHTML='<div class="empty">正在生成合同呈现与改动清单…</div>';
    try{
      const docs=await reviewDocumentList(doc);
      if(!current(t)||state.detail!==doc || $('detail-overlay').hidden) return;
      const base=doc.review_url || `${pathDoc(doc)}/revisions`;
      const view=await json(base);
      if(!current(t)||state.detail!==doc || $('detail-overlay').hidden) return;
      const selectionEpoch=Number.isInteger(view.selection_epoch)?view.selection_epoch:0;
      const manifestHash=typeof view.manifest_hash==='string'?view.manifest_hash:'';
      const draftBinding=JSON.stringify({epoch:selectionEpoch,manifest:manifestHash,revisions:view.revisions});
      let chosen=state.reviewDecisions.get(doc.document_id)||{};
      try{const saved=JSON.parse(sessionStorage.getItem(reviewDraftKey(doc))||'null');if(saved?.binding===draftBinding)chosen=saved.chosen||{};}catch{}
      const first=view.revisions&&view.revisions[0];
      state.review={...view,doc,chosen,draftBinding,selectionEpoch,manifestHash,active:first?first.del_id:null,docs};
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
    go('document',{id:state.selected,document:target.document_id,tab:'review'});
  }
  function closeReview(){reviewDecisionsSave();state.review=null;state.tokens.review=(state.tokens.review||0)+1;const doc=state.detail;if(doc)go('document',{id:state.selected,document:doc.document_id});}
  async function generateSelected(all){
    const doc=state.detail; let review=state.review; if(!doc||state.selectionBusy) return;
    const operation={epoch:state.epoch,doc};state.selectionBusy=operation;
    const active=()=>identityCurrent(operation.epoch)&&state.selectionBusy===operation;
    const label=selectedContractLabel(doc);
    const controls=[...$('detail-body').querySelectorAll('button,input')].map(el=>({el,disabled:el.disabled}));controls.forEach(({el})=>el.disabled=true);
    const message=$('review-message');
    if(message) message.textContent=`正在生成${label}…`;
    try{
      let selectionEpoch=review?review.selectionEpoch:null;
      let manifestHash=review?review.manifestHash:'';
      if((selectionEpoch==null||!manifestHash)&&doc.review_url){
        try{const view=await json(doc.review_url);if(!active())return;selectionEpoch=Number.isInteger(view.selection_epoch)?view.selection_epoch:0;manifestHash=typeof view.manifest_hash==='string'?view.manifest_hash:'';}catch(e){if(!active())return;if(e.code!==409){const wrapped=new Error(`读取修订状态未完成：${humanErrorText(e,'响应格式异常，请稍后重试。')}`);wrapped.code=e.code;wrapped.raw=e.raw;wrapped.prelude=true;throw wrapped;}}
      }
      const decisions=all==='accept'?null:review?review.revisions.map(r=>({del_id:r.del_id,
        decision:(review.chosen||{})[r.del_id]||'accept'})):null;
      const binding={selection_epoch:selectionEpoch??0,...(manifestHash?{manifest_hash:manifestHash}:{})};
      const selectionBody=all==='accept'?binding:{...binding,decisions};
      const url=all==='accept'?`${pathDoc(doc)}/accept-all`:`${pathDoc(doc)}/decisions`;
      const result=await json(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(selectionBody)});
      if(!active())return;
      const accepted=(result.accepted||[]).length, rejected=(result.rejected||[]).length;
      if(state.detail!==doc||$('detail-overlay').hidden){toast(`${doc.name}：${label}已生成，可重新打开报告下载。`);return;}
      if(message) message.textContent=`已生成${label}：接受 ${accepted} 条，拒绝 ${rejected} 条。`;
      await refresh();
      if(!active()||state.detail!==doc||$('detail-overlay').hidden)return;
      if(review&&state.review===review){if(Number.isInteger(result.selection_epoch))review.selectionEpoch=result.selection_epoch;if(typeof result.manifest_hash==='string')review.manifestHash=result.manifest_hash;}
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
      const conflict=e.raw==='SELECTION_EPOCH_REQUIRED'||e.raw==='SELECTION_EPOCH_CONFLICT'||e.raw==='SELECTION_MANIFEST_CONFLICT';
      if(message&&state.detail===doc) message.textContent=conflict?'选择版本已变化，已重新读取当前修订；请确认后重试。':e.prelude?e.message:'生成失败，请稍后重试。';
      if(conflict)await openReview(doc);
      else errorNotice(e);
    }finally{if(active()){state.selectionBusy=null;controls.filter(({el})=>el.isConnected).forEach(({el,disabled})=>el.disabled=disabled);}}
  }
  // FL-D896 结果页信息架构：阅读顺序=用户三连问——L0 改完没（结论条）→L1 改了哪些→L2 还要人工核→L3 接下来怎么做→L4 判定依据；其余降级收起。
  // FL-D1065③ 结论三块合一：状态徽章+修改数+入口动作一句话，宽屏一行、窄屏折行不溢出。
  function resultActionHint(usable,withExceptions,evaluation,hasFinal,hasRedline,processing,displayedJob,eligibility){
    if(eligibility==='excluded_by_fund_type')return '';
    if(evaluation)return hasFinal?'下方可下载评测版核对修改效果。':'';
    if(usable&&hasFinal)return '下方可下载最终版合同，需要逐条核对时先进入修订审查。';
    if(withExceptions&&hasFinal)return '核完上方例外清单后，下方下载最终版使用。';
    if(displayedJob==='paused')return '恢复任务后继续处理。';
    if(processing)return '处理完成后本页自动更新。';
    if(hasRedline)return '下方进入修订审查，逐条核对改动。';
    return '';
  }
  function resultStatusWord(delivery,eligibility,evaluation,displayedJob,processing,usable,withExceptions){
    if(evaluation)return {word:'评测结果 · 非正式合同',cls:'b-blue'};
    if(usable)return {word:'已完成 · 可下载使用',cls:'b-green'};
    if(withExceptions)return {word:'已完成 · 需人工核对',cls:'b-amber'};
    if(eligibility==='excluded_by_fund_type')return {word:'不适用 · 已排除',cls:'b-gray'};
    if(displayedJob==='paused')return {word:'已暂停',cls:'b-gray'};
    if(processing)return {word:'正在处理',cls:'b-blue'};
    if(delivery==='incomplete')return {word:'处理完成',cls:'b-green'};
    return {word:'尚未交付',cls:'b-gray'};
  }
  // L0 不再放按钮：结论条只答「改完没」；行动权全部归 L3 行动面板（FL-D1018，避免 hero/面板重复按钮）。
  // FL-D1018 行动区重塑：下载区=独立行动面板（主行动行+产物清单，行式直连不再收起）；审阅修订入口与下载同权（36px 同尺寸同行）。杜绝大框放小按钮。
  // FL-D997 口径：按钮只显示中文标签；labels 缺键即跳过，绝不裸 kind。
  const RESULT_FILE_LABELS={final:'最终版',redline:'带修改标记版',selected_final:'选择版',selected_redline:'选择版-带修改标记',working_final:'修改版',working_redline:'修改版-带修改标记',report_md:'文本报告',report_json:'原始数据（JSON）',evaluation_final:'评测版（非正式）',evaluation_redline:'评测版-带修改标记'};
  // FL-D1065① 下载区=一横排按钮流：打开修订审查（最前）→ 产物（最终版主钮+其余同排）→ 一键接受全部修订（收尾）；取消分组小标题。
  function artifactButtons(doc,usable,exclude=[]){
    const downloads=doc.downloads || {};
    const labels=RESULT_FILE_LABELS;
    const available=kind=>downloads[kind]&&labels[kind]&&!exclude.includes(kind)&&!(kind==='final'&&!usable);
    const groups=[['对照与审阅',['final','redline','selected_final','selected_redline','evaluation_final','evaluation_redline','working_final','working_redline']],['报告与数据',['report_md','report_json']]];
    return groups.map(([title,names])=>{const list=names.filter(available);if(!list.length)return '';return `<span class="btn-group-label">${title}</span>`+list.map(kind=>`<button class="btn btn-sm${['final','working_final','evaluation_final'].includes(kind)?' btn-mid':''}" data-download="${kind}">${labels[kind]}</button>`).join('');}).join('');
  }
  function nextSection(doc,report,delivery,eligibility,displayedJob,processing,usable,withExceptions,evaluation,rc){
    const downloads=doc.downloads || {};
    const hasRedline=Boolean(downloads.working_redline || downloads.redline);
    let guide;
    const hasFinal=Boolean(downloads.final);
    if(evaluation)guide='评测版仅供核对修改效果，不能作为正式合同；正式交付请使用正式任务。';
    else if(usable)guide=!hasFinal?'已全部改完；最终版尚未生成，可先打开修订审查逐条核对。':(rc.unresolved?`先核完上方 ${rc.unresolved} 处人工核对项，再下载最终版使用。`:'已改完全部条款，可直接下载最终版使用；需要逐条核对时打开修订审查。');
    else if(withExceptions)guide=!hasFinal?`先核完上方 ${rc.unresolved||'以上'} 处人工核对项；最终版尚未生成，请勿直接使用工作文件。`:`先核完上方 ${rc.unresolved||'以上'} 处人工核对项，再下载最终版使用；未自动修改处请以例外清单为准。`;
    else if(eligibility==='excluded_by_fund_type')guide='该基金类型不在本流程范围，本文件不参与修改。';
    else if(displayedJob==='paused')guide='任务已暂停，恢复任务后将继续处理；处理完成后状态会自动更新。';
    else if(processing)guide='正在处理，完成后本页会自动更新，无需手动刷新。';
    else if(delivery==='incomplete')guide='部分条款未自动修改，本文件不能直接使用；先逐条核对上方人工核对项，再决定是否下载工作文件。';
    else guide='尚未生成可交付文件；如长时间无进展，请返回任务列表查看其他文件状态。';
    // FL-D1065(2) 修订操作组=key 功能红回填（btn-primary 强主红）；交付件=次强 btn-mid。
    const opsGroup=!evaluation&&hasRedline?`<span class="btn-group-label">修订操作</span><button class="btn btn-sm btn-primary" data-action="open-review">打开修订审查</button><button class="btn btn-sm" data-action="accept-all">一键接受全部修订</button>`:'';
    const files=artifactButtons(doc,usable||withExceptions);
    const anyButton=opsGroup||files;
    const actionRow=anyButton?`<div class="detail-actions result-action-row" id="revision-section">${files}${opsGroup}</div>${hasRedline&&!evaluation?'<p class="subnote" id="review-status"></p>':''}`:'';
    const hint=anyButton?'<p class="subnote result-files-hint">对照与工作文件供审阅对照；文本报告为 Markdown，原始数据为 JSON。</p>':'';
    return `<section class="detail-section result-next"><h3>接下来怎么做</h3><p>${esc(guide)}</p>${actionRow}${hint}</section>`;
  }
  function renderReport(doc,report) {
    if(isDirectReport(report)||(isDirectDoc(doc)&&doc.outcome)){renderDirectReport(doc,report);return;}
    const delivery=report?.delivery_status || doc.delivery_status,eligibility=report?.qualification_status || doc.eligibility;
    // FL-D1065② 状态口径：交付态=complete家族即按已交付处理，不再被 eligibility=pending（遗留/未判定）降级成「尚未交付」造成同屏矛盾；excluded 依旧排除。
    const excluded=eligibility==='excluded_by_fund_type';
    const usable=!excluded&&delivery==='complete',withExceptions=!excluded&&delivery==='complete_with_exceptions';
    const evaluation=(delivery||'').startsWith('evaluation_')||doc.execution_mode==='evaluation';
    const displayedJob=displayJobStatus(doc);
    const processing=['queued','running','leased','retry_wait'].includes(displayedJob);
    const rc=resultCounts(report,doc);
    const status=resultStatusWord(delivery,eligibility,evaluation,displayedJob,processing,usable,withExceptions);
    const headline=rc.total?(rc.unresolved?`改完 ${rc.completed}/${rc.total} 处 · 待人工核 ${rc.unresolved} 处`:`改完 ${rc.completed}/${rc.total} 处 · 无需人工核`):status.word;
    const heroHint=resultActionHint(usable,withExceptions,evaluation,Boolean(doc.downloads&&(doc.downloads.final||doc.downloads.evaluation_final)),Boolean(doc.downloads&&(doc.downloads.working_redline||doc.downloads.redline)),processing,displayedJob,eligibility);
     const reasonText=docReason({...doc,delivery_status:delivery,eligibility});
    const notes=[reasonText];
    if(evaluation)notes.push('评测文件不能作为正式合同。');
    if(report?.has_toc_field===true)notes.push('下载后请在 Word 中更新目录。');
    if(state.task?.legacy)notes.push('遗留任务只读，不能补传或重新修订。');
    if(report?.verification_status==='verification_blocked')notes.push('验证暂未完成，恢复任务后将继续校验；当前文件尚未通过最终交付核验。');
    let html=`<section class="result-summary" aria-label="结论">
      <p class="result-hero-label">结论</p>
      <div class="result-hero-head"><span class="badge ${status.cls} result-hero-status">${esc(status.word)}</span><strong class="result-hero-line">${esc(headline)}</strong>${heroHint?`<span class="result-hero-hint">${esc(heroHint)}</span>`:''}</div>
      ${notes.filter(Boolean).map(n=>`<p class="result-hero-note">${esc(n)}</p>`).join('')}</section>`;
    if(report){
      const summary=report.user_summary;
      const rows=changedClauses(report,doc);
      // FL-D896 N1：0 改动态给明确空态句（已交付/本身符合时），比整块缺失更可读
      const clausesHTML=rows.length?`<section class="detail-section"><h3>改了哪些条款 · ${rows.length} 处</h3>${rows.map(clauseRow).join('')}</section>`
        :(['complete','complete_with_exceptions','evaluation_unmodified'].includes(delivery)?'<section class="detail-section"><h3>改了哪些条款 · 0 处</h3><p class="subnote">报告未列出条款改动。</p></section>':'');
      html+=clausesHTML+unresolvedIssuesHTML(report,summary);
    }else html+='<p class="result-pending">报告尚未生成，处理完成后可查看。</p>';
    html+=nextSection(doc,report,delivery,eligibility,displayedJob,processing,usable,withExceptions,evaluation,rc);
    const showBasis=report&&(delivery==='diagnosed'||(eligibility&&!['eligible','pending'].includes(String(eligibility))));
    if(showBasis){html+=`<section class="detail-section"><h3>${eligibility==='excluded_by_fund_type'?'为什么不能处理':'判定依据'}</h3>${eligibilityEvidenceHTML(report)||`<p>${esc(reasonText||'报告未提供判定说明。')}</p>`}</section>`;}
    $('detail-body').innerHTML=html;
  }
  function eligibilityEvidenceHTML(report) {const src=report.qualification || report.eligibility || {};const items=[];const quote=src.fund_type_quote;if(quote)items.push(proof(quote));if(src.fund_type_basis)items.push(`<p class="subnote">${esc(src.fund_type_basis)}</p>`);else if(src.basis)items.push(`<p class="subnote">依据：${esc(src.basis)}</p>`);const extra=report.qualification?.evidence || report.eligibility?.evidence || report.qualification_evidence || [];const list=Array.isArray(extra)?extra:[extra];for(const item of list)items.push(proof(item));return items.join('');}
  async function showDetail(doc) {
    if(!doc)return;
    if(state.view!=='document'||state.route?.document!==doc.document_id){go('document',{id:state.selected,document:doc.document_id});return;}
    reviewDecisionsSave();state.review=null;state.tokens.review=(state.tokens.review||0)+1;
    const t=ticket('detail'),id=state.selected;state.detail=doc;
    $('detail-title').textContent=doc.name;renderBreadcrumb();$('detail-body').innerHTML='<div class="empty">正在读取合同状态与报告…</div>';$('detail-overlay').hidden=false;
    try{const report=doc.report_url?await json(doc.report_url):null;if(!current(t)||state.selected!==id||$('detail-overlay').hidden)return;renderReport(doc,report);}
    catch(e){if(current(t)){$('detail-body').innerHTML='<div class="empty">报告暂无法读取，请返回后重试。</div>';errorNotice(e);}}
  }
  function closeDetail() {reviewDecisionsSave();state.review=null;state.tokens.review=(state.tokens.review||0)+1;if(!$('detail-overlay').hidden){$('detail-overlay').hidden=true;document.querySelector('.app').inert=false;state.focusReturn?.focus();}state.tokens.detail=(state.tokens.detail || 0)+1;state.detail=null;$('detail-body').replaceChildren();$('detail-title').textContent='';}
  function resetWorkspace(){document.dispatchEvent(new Event('fundlex:identity-reset'));$('toast').replaceChildren();$('toast').hidden=true;showToast.recent={};$('help-overlay').hidden=true;$('notification-toggle').setAttribute('aria-expanded','false');notifications.length=0;taskStatuses=new Map();state.modelData=null;state.modelEdit=null;state.modelVerified={};state.modelCopyFrom=null;$('notification-panel').hidden=true;renderNotifications();state.epoch++;state.importSession++;state.controllers.forEach(c=>c.abort());state.controllers.clear();state.tokens={};state.selected=null;state.task=null;state.tasks=[];state.tasksLoaded=false;state.tasksFailed=false;state.cap=null;state.overviewStats=null;state.taskGuides=null;state.imports=[];state.recover=null;state.createKey=null;state.uploadToken=null;state.uploading=false;state.uploadProgress=null;state.replaceTarget=null;state.reviewDocs=null;state.reviewDocsTask=null;state.reviewDocsKey='';state.review=null;state.reviewDecisions=new Map();state.selectionBusy=null;state.guideDismissed=(()=>{try{return localStorage.getItem(`fundlex-guide-dismissed:${localStorage.getItem('fundlex-dev-user')||'user'}`)==='1';}catch{return false;}})();$('user-rows').replaceChildren();for(const id of ['new-user-name','new-user-display','new-user-password','pwd-old','pwd-new','pwd-confirm','register-password','register-confirm'])$(id).value='';$('password-view').hidden=true;for(const id of ['user-create-btn','pwd-submit'])$(id).disabled=false;for(const id of ['user-create-error','pwd-error']){$(id).textContent='';$(id).hidden=true;}state.taskPage=state.importPage=state.docPage=1;state.taskDocs=[];closeDetail();$('task-rows').innerHTML=emptyRow(7,'正在读取任务');$('doc-rows').innerHTML=emptyRow(7,'请选择当前身份的任务');$('task-pagination').replaceChildren();$('doc-pagination').replaceChildren();$('task-name').value='';$('detail-title').textContent='';$('task-guide-meta').hidden=true;$('task-guide-value').textContent='';$('doc-reason-filter').innerHTML='<option value="">全部原因</option>';window.FundLexSelectKit?.feed($('doc-reason-filter'));$('upload-message').textContent='选择文件后检查清单，开始上传任务。';resetGuides();$('file-picker').value='';$('folder-picker').value='';$('replace-picker').value='';for(const id of ['task-search','import-search','doc-search'])$(id).value='';for(const id of ['task-filter','task-guide-filter','import-filter','doc-upload-filter','doc-qualification-filter','doc-completeness-filter','doc-status-filter','doc-reason-filter','doc-sort'])$(id).value='';syncFirstRunGuide();renderTaskGuideFilter();renderTask();renderImport();renderTopbarTitle(state.view);renderBreadcrumb(state.view);renderFooter();}
  function identityChanged(){resetWorkspace();hideLogin();try{localStorage.setItem('fundlex-dev-user',owner());}catch{}clearTimeout(identityChanged.timer);identityChanged.timer=setTimeout(()=>refresh(true),350);}
  async function loadMe(){const user=await json('/api/auth/me');setAuthSession(state.auth.token,user);return user;}
  function handleSessionExpired(){if(state.auth.mode!=='password')return;if(!state.auth.token&&!state.auth.user)return;clearAuthSession();resetWorkspace();showLogin('登录状态已失效，请重新登录。');}
  async function submitLogin(event){event.preventDefault();const username=$('login-username').value.trim(),password=$('login-password').value,button=$('login-submit'),box=$('login-error');if(!username||!password){box.textContent='请输入用户名和密码。';box.hidden=false;return;}button.disabled=true;box.hidden=true;try{const response=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password}),cache:'no-store'});let payload=null;try{payload=await response.json();}catch{}if(!response.ok){const detail=payload&&typeof payload.detail==='string'?payload.detail:'';throw new Error(response.status===401?'用户名或密码不正确。':response.status===403?'账号已被禁用，请联系管理员。':response.status===404?'当前环境未启用账号登录。':detail||'登录未完成，请稍后重试。');}if(!payload||!payload.token||!payload.user)throw new Error('登录响应未通过格式校验，请稍后重试。');state.auth.mode='password';setAuthSession(payload.token,payload.user);hideLogin();await refresh(true);openDeepLinkedTask();}catch(e){if(e&&e.name!=='AbortError'){box.textContent=humanErrorText(e,'登录未完成，请稍后重试。');box.hidden=false;}}finally{button.disabled=false;}}
  async function logout(){const token=state.auth.token;clearAuthSession();resetWorkspace();showLogin('已退出登录。','info');try{await fetch('/api/auth/logout',{method:'POST',headers:token?{'Authorization':`Bearer ${token}`}:{},cache:'no-store'});}catch{}}
  function openPasswordDialog(){const view=$('password-view');if(!view||!state.auth.user)return;view.hidden=false;document.querySelector('.app').inert=true;$('pwd-error').hidden=true;$('pwd-old').value='';$('pwd-new').value='';$('pwd-confirm').value='';$('pwd-old').focus();}
  function closePasswordDialog(){const view=$('password-view');if(!view||view.hidden)return;view.hidden=true;if($('login-view').hidden)document.querySelector('.app').inert=false;}
  async function submitPasswordChange(event){event.preventDefault();const epoch=state.epoch;const oldP=$('pwd-old').value,newP=$('pwd-new').value,confirmP=$('pwd-confirm').value,box=$('pwd-error'),button=$('pwd-submit');const fail=message=>{box.textContent=message;box.hidden=false;};box.hidden=true;if(!oldP||!newP||!confirmP)return fail('请填写全部密码字段。');if(newP.length<8)return fail('新密码至少 8 位。');if(newP!==confirmP)return fail('两次输入的新密码不一致。');button.disabled=true;try{const response=await fetch('/api/auth/password',{method:'POST',headers:{'Content-Type':'application/json',...(state.auth.token?{'Authorization':`Bearer ${state.auth.token}`}:{})},body:JSON.stringify({old_password:oldP,new_password:newP}),cache:'no-store'});if(!identityCurrent(epoch))return;let payload=null;try{payload=await response.json();}catch{}if(!identityCurrent(epoch))return;if(!response.ok){const detail=payload&&typeof payload.detail==='string'?payload.detail:'';if(response.status===401){let sessionAlive=false;try{const me=await fetch('/api/auth/me',{headers:state.auth.token?{'Authorization':`Bearer ${state.auth.token}`}:{},cache:'no-store'});sessionAlive=me.ok;}catch{}if(!identityCurrent(epoch))return;if(sessionAlive)return fail('当前密码不正确。');closePasswordDialog();handleSessionExpired();return;}return fail(detail||'修改失败，请稍后重试。');}closePasswordDialog();toast('密码已更新，其它设备需重新登录。');}catch{if(!identityCurrent(epoch))return;fail('无法连接本地服务，请稍后重试。');}finally{if(identityCurrent(epoch))button.disabled=false;}}
  async function submitRegister(event){event.preventDefault();const username=$('register-username').value.trim(),display=$('register-display').value.trim(),password=$('register-password').value,confirm=$('register-confirm').value,box=$('register-error'),button=$('register-submit');const fail=message=>{box.textContent=message;box.hidden=false;};box.hidden=true;if(username.length<3)return fail('用户名至少 3 位。');if(!/^[A-Za-z0-9_.-]+$/.test(username))return fail('用户名只能使用字母、数字或 _ . -。');if(password.length<8)return fail('密码至少 8 位。');if(password!==confirm)return fail('两次输入的密码不一致。');button.disabled=true;try{const response=await fetch('/api/auth/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password,display_name:display}),cache:'no-store'});let payload=null;try{payload=await response.json();}catch{}if(!response.ok){const detail=payload&&typeof payload.detail==='string'?payload.detail:'';if(response.status===409)return fail('该用户名已被注册，请更换。');if(response.status===403)return fail('当前环境未开放注册。');if(response.status===422)return fail('输入不符合要求，请检查用户名与密码。');return fail(detail||'注册未完成，请稍后重试。');}state.auth.mode='password';setAuthSession(payload.token,payload.user);resetWorkspace();hideLogin();refresh(true).then(openDeepLinkedTask);}catch{fail('无法连接本地服务，请稍后重试。');}finally{button.disabled=false;}}
  async function loadUsers(){const t=ticket('users'),rows=$('user-rows');rows.setAttribute('aria-busy','true');try{const payload=await json('/api/admin/users');if(!current(t))return;const users=(payload&&payload.users)||[];rows.innerHTML=users.map(u=>{const ts=u.created_at>1e12?u.created_at:u.created_at*1000;const self=state.auth.user&&u.id===state.auth.user.id;return `<tr><td><span class="filename">${esc(u.username)}</span>${self?'<span class="row-sub">当前登录账号</span>':''}</td><td>${esc(u.display_name||'—')}</td><td>${u.role==='admin'?'管理员':'成员'}</td><td>${u.disabled?badge('failed','已禁用'):badge('succeeded','正常')}</td><td>${esc(new Date(ts).toLocaleString('zh-CN'))}</td><td>${self?'':`<button class="btn-link" data-user-toggle="${esc(u.id)}" data-user-disabled="${u.disabled?1:0}">${u.disabled?'启用':'禁用'}</button>`}</td></tr>`;}).join('')||emptyRow(6,'当前没有可显示的账号');}catch(e){if(current(t)){rows.innerHTML=emptyRow(6,'账号列表暂未加载，请刷新后重试');errorNotice(e);}}finally{if(current(t))rows.removeAttribute('aria-busy');}}
  async function toggleUser(id,disabled){const t=ticket('users');try{const response=await fetch(`/api/admin/users/${encodeURIComponent(id)}/disable`,{method:'POST',headers:{'Content-Type':'application/json',...(state.auth.token?{'Authorization':`Bearer ${state.auth.token}`}:{})},body:JSON.stringify({disabled}),cache:'no-store'});if(!identityCurrent(t.epoch))return;if(response.status===401){handleSessionExpired();return;}if(!response.ok){let detail='';try{const p=await response.json();detail=typeof p.detail==='string'?p.detail:'';}catch{}throw new Error(detail||'操作未完成，请稍后重试。');}if(!current(t))return;toast(disabled?'账号已禁用，其登录会话已失效。':'账号已启用。');await loadUsers();}catch(e){if(current(t))errorNotice(e);}}
  async function createUser(){const epoch=state.epoch;const username=$('new-user-name').value.trim(),display=$('new-user-display').value.trim(),role=$('new-user-role').value,password=$('new-user-password').value,box=$('user-create-error'),button=$('user-create-btn');const fail=message=>{box.textContent=message;box.hidden=false;};box.hidden=true;if(username.length<3)return fail('用户名至少 3 位。');if(!/^[A-Za-z0-9_.-]+$/.test(username))return fail('用户名只能使用字母、数字或 _ . -。');if(password.length<8)return fail('初始密码至少 8 位。');button.disabled=true;try{const response=await fetch('/api/admin/users',{method:'POST',headers:{'Content-Type':'application/json',...(state.auth.token?{'Authorization':`Bearer ${state.auth.token}`}:{})},body:JSON.stringify({username,password,display_name:display,role}),cache:'no-store'});if(!identityCurrent(epoch))return;if(response.status===401){handleSessionExpired();return;}if(!response.ok){let detail='';try{const p=await response.json();detail=typeof p.detail==='string'?p.detail:'';}catch{}if(!identityCurrent(epoch))return;if(response.status===409)return fail('该用户名已存在。');if(response.status===422)return fail('输入不符合要求，请检查用户名与密码。');return fail(detail||'创建未完成，请稍后重试。');}$('new-user-name').value='';$('new-user-display').value='';$('new-user-password').value='';$('new-user-role').value='member';toast('账号已创建，请将用户名与初始密码告知本人。');await loadUsers();}catch{if(!identityCurrent(epoch))return;fail('无法连接本地服务，请稍后重试。');}finally{if(identityCurrent(epoch))button.disabled=false;}}
  const GUIDE_STATUSES=window.FUNDLEX_GUIDE_STATUSES||{uploaded:'待解析',parsing:'解析中',parsed:'已解析',validated:'校验通过',parse_failed:'解析失败',failed:'解析失败',released:'已发布',archived:'已归档'};
  const GUIDE_ENABLEABLE=['parsed','released'],GUIDE_PARSEABLE=['uploaded','parse_failed','parsed','failed'];
  const shortHash=value=>value?String(value).slice(0,12):'—';
  const guideStatusLabel=value=>GUIDE_STATUSES[value] || '未确认';
  const guideTime=value=>value?new Date(value>1e12?value:value*1000).toLocaleString('zh-CN'):'—';
  const guideKind=item=>item.built_in?'<span class="badge b-gray">内置</span>':'<span class="badge b-blue">自定义</span>';
  // FL-D1121（用户令 2026-11-04）：内置默认指引显示名=「修改指引V2」（只改展示,不写库）。
  const guideDisplayName=item=>(item&&item.built_in)?'修改指引V2':(item&&item.filename)||'指引';
  const guideCurrentFlag=item=>item.current?'<span class="badge b-green">当前使用</span>':'';
  const guideByName=id=>(state.guides || []).find(item=>item.id===id) || null;
  const guideReady=()=>!!state.cap?.engine?.guide&&state.cap.engine.delivery_mode==='formal';
  // （旧 guide-rules-v1 的 guideOps noop 枚举渲染已随旧格式兼容展示一并物理删除）
  function renderGuideBinding() {const box=$('guide-binding');if(!box)return;const cap=state.cap,guide=cap?.engine?.guide || null;box.hidden=false;if(!cap){box.className='guide-binding';box.textContent='当前指引尚未加载，请稍后重试。';return;}
    if(guide&&guideReady()){box.className='guide-binding';box.innerHTML=`本任务将使用指引：<strong>${esc(guideDisplayName(guide))}</strong>（版本 ${esc(shortHash(guide.id))} · 指引规则 ${guide.groups || 0} 条 · ${esc(guideStatusLabel(guide.status))}）${guideKind(guide)}<br><span class="subnote">启用新指引只影响之后创建的任务；已在处理的任务仍用创建时绑定的版本。</span>`;return;}
    box.className='guide-binding guide-binding-warning';box.innerHTML='当前指引不可用：暂时不能创建任务。请先到 <button type="button" class="btn-link" data-nav="guide">指引配置</button> 启用可用指引，再刷新本页。';}
  function resetGuides() {state.guides=null;state.guidesFailed=false;state.guideBusy=null;state.guideUploading=false;clearTimeout(state.guideTimer);state.guideTimer=null;const input=$('guide-file');if(input)input.value='';const name=$('guide-file-name');if(name)name.textContent='尚未选择文件';const button=$('guide-upload-btn');if(button)button.disabled=true;const message=$('guide-upload-message');if(message)message.textContent='解析失败可在列表中查看问题并重新解析。';$('guide-rows').innerHTML=emptyRow(7,'正在读取指引列表');$('guide-current-body').textContent='正在读取当前指引…';$('guide-current-flags').replaceChildren();$('guide-list-state').textContent='';$('guide-reset-btn').disabled=true;$('guide-reset-btn').title='恢复内置指引并用于之后创建的任务';closeGuidePanel();}
  async function loadGuides(quiet=false) {if(state.auth.mode==='password'&&!state.auth.token)return;const t=ticket('guide'),rows=$('guide-rows');if(!quiet){rows.setAttribute('aria-busy','true');$('guide-list-state').textContent='正在读取指引列表…';}
    try{const payload=await json('/api/guides');if(!current(t))return;state.guides=Array.isArray(payload.items)?payload.items:[];state.guidesFailed=false;renderGuides();}
    catch(e){if(!current(t))return;state.guides=null;state.guidesFailed=true;rows.innerHTML=emptyRow(7,e.code===404?'当前环境未提供指引配置接口':'指引列表暂未加载，请检查连接后刷新');$('guide-list-state').textContent='';$('guide-current-body').innerHTML=`<p class="subnote">${esc(e.code===404?'当前环境未提供指引配置接口，或该账号暂不可访问；请稍后重试。':'当前指引暂不可读；请稍后重试。')}</p>`;$('guide-current-flags').replaceChildren();$('guide-reset-btn').disabled=true;if(e.code!==404)errorNotice(e);}
    finally{if(current(t))rows.removeAttribute('aria-busy');}}
  function renderGuides() {const items=state.guides || [],current=items.find(item=>item.current) || null,busy=!!state.guideBusy;
    $('guide-current-flags').innerHTML=current?guideKind(current)+guideCurrentFlag(current):'';
    $('guide-current-body').innerHTML=current?`<dl class="detail-grid"><dt>文件名</dt><dd><span class="filename" title="${esc(current.filename)}">${esc(current.filename)}</span></dd><dt>状态</dt><dd>${badge(current.status, GUIDE_STATUSES[current.status])}</dd><dt>规则条数</dt><dd>${current.groups} 条</dd><dt>版本</dt><dd>${esc(shortHash(current.id))}</dd></dl>`:'<p class="subnote">尚未确定当前指引。请刷新列表，或上传并启用一个已解析的自定义指引。</p>';
    $('guide-rows').innerHTML=items.map(item=>{const enable=GUIDE_ENABLEABLE.includes(item.status),parse=!item.built_in&&GUIDE_PARSEABLE.includes(item.status);
      return `<tr><td><span class="filename" title="${esc(item.filename)}">${esc(guideDisplayName(item))}</span>${item.parent_version_id?'<span class="row-sub">由旧版本重新解析而来</span>':''}</td><td>${badge(item.status, GUIDE_STATUSES[item.status])}</td><td>${item.groups} 条</td><td>${item.issues} 项</td><td>${guideKind(item)}${guideCurrentFlag(item)}</td><td>${esc(guideTime(item.created_at))}</td><td><div class="guide-actions"><button class="btn-link" data-guide-enable="${esc(item.id)}" ${busy||item.current||!enable?'disabled':''} title="${item.current?'该指引当前正在使用':enable?'新任务改用该指引':'解析完成后才能启用'}">启用指引</button><button class="btn-link" data-guide-diff="${esc(item.id)}">版本对比</button><button class="btn-link" data-guide-issues="${esc(item.id)}" ${busy?'disabled':''}>解析详情</button></div></td></tr>`;}).join('') || emptyRow(7,'还没有可用指引');
    $('guide-list-state').textContent=items.length?`共 ${items.length} 个版本 · 解析成功并形成可执行指引卡后即成为之后任务的默认指引；手动启用其他版本只影响之后创建的任务，解析中或解析失败的版本不会被使用。`:'';
    $('guide-reset-btn').disabled=busy||!current||!!current.built_in;
    $('guide-reset-btn').title=current&&current.built_in?'当前已使用内置指引':'恢复内置指引并用于之后创建的任务';
    refreshGuideDiffCard();
    guidePolling();}
  function guidePolling() {clearTimeout(state.guideTimer);state.guideTimer=null;if(state.view!=='guide')return;if(!(state.guides || []).some(item=>item.status==='uploaded'||item.status==='parsing'))return;const epoch=state.epoch;state.guideTimer=setTimeout(()=>{if(identityCurrent(epoch)&&state.view==='guide')loadGuides(true);},4000);}
  // ── 指引版本对比（规则差异 + 原文比对；全确定性，不调模型）──────────────────
  // ── 指引版本对比（弹窗式，照抄合同比对查看器；只读、无「采用 A/B」；仅原文比对）──
  function guideDiffLabel(item){return `${guideDisplayName(item)} · ${esc(guideTime(item.created_at))}${item.current?'（当前）':''}${item.built_in?'（内置）':''}`;}
  // FL-D1087（用户令「内置要进下拉」）：自定义在前、内置殿后；内置以服务端 canonical 参与比对。
  function gdUploaded(){const items=[...(state.guides||[])];
    const customs=items.filter(item=>!item.built_in).sort((a,b)=>(b.created_at||0)-(a.created_at||0));
    const builtins=items.filter(item=>item.built_in).sort((a,b)=>(b.created_at||0)-(a.created_at||0));
    return [...customs,...builtins];}
  function refreshGuideDiffCard(){const from=$('gd-diff-from'),to=$('gd-diff-to'),start=$('gd-diff-start');if(!from||!to)return;const d=state.guideDiff||=({from:'',to:'',view:'word',filter:'',td:null,items:[],cursor:-1});
    d.prog=true;setTimeout(()=>{if(state.guideDiff===d)d.prog=false;},700);
    const uploaded=gdUploaded();
    if(uploaded.length<2){from.innerHTML='';to.innerHTML='';from.disabled=to.disabled=true;if(start)start.disabled=true;d.from=d.to='';return;}
    from.disabled=to.disabled=false;if(start)start.disabled=false;
    const valid=sel=>uploaded.some(item=>item.id===d[sel]&&item.id!==d[sel==='from'?'to':'from']);
    if(!valid('to'))d.to=uploaded[0].id;
    if(!valid('from'))d.from=(uploaded.find(item=>item.id!==d.to)||uploaded[1]).id;
    const options=sel=>uploaded.map(item=>`<option value="${esc(item.id)}" ${item.id===d[sel]?'selected':''}>${guideDiffLabel(item)}</option>`).join('');
    from.innerHTML=options('from');to.innerHTML=options('to');
    from.value=d.from;to.value=d.to;
    // 两个选择器原生渲染（data-fl-selectvend=off 退出 SlimSelect 托管——回声写脏下拉值的前科，FL-D1071）。
  }
  function gdBindSplittersOnce(){if(state._gdSplitBound||!window.FundLexColumnSplitter)return;state._gdSplitBound=true;
    window.FundLexColumnSplitter($('gd-rail-splitter'),$('gd-diff-body'),document.querySelector('#gd-diff-body .compare-diff-rail'),{
      key:'fundlex-gd-diff-revisions-width',variable:'--gd-rail-w',min:220,max:660,minOther:480,fallback:300,side:'left',
      disabled:()=>matchMedia('(max-width: 760px)').matches});
    window.FundLexColumnSplitter($('gd-src-splitter'),$('gd-diff-word-layout'),$('gd-diff-sources'),{
      key:'fundlex-gd-diff-sources-width',variable:'--gd-src-w',min:240,max:720,minOther:480,fallback:320,side:'right',
      disabled:()=>matchMedia('(max-width: 760px)').matches||!state.guideDiff||state.guideDiff.view==='classic'||state.guideDiff.showSources===false});}
  function openGuideDiffModal(toId){const viewer=$('gd-diff-viewer');if(!viewer)return;const d=state.guideDiff||=({from:'',to:'',view:'word',filter:'',td:null,items:[],cursor:-1});
    gdBindSplittersOnce();
    if(toId){const uploaded=gdUploaded();if(uploaded.some(item=>item.id===toId)){d.to=toId;const base=uploaded.find(item=>item.id!==toId);d.from=base?base.id:'';}}
    refreshGuideDiffCard();
    d.td=null;d.items=[];d.cursor=-1;d.filter='';const filterSel=$('gd-diff-filter');if(filterSel)filterSel.value='';
    $('gd-diff-body').hidden=true;$('gd-diff-empty').hidden=false;
    $('gd-diff-empty').textContent=gdUploaded().length<2?'当前只有一份可比版本的指引；再上传一份指引，就能直接与之比对。':'选好两个版本后点「开始对比」，结果会显示在这里；对比完全在服务器本地计算，不调用模型。';
    $('gd-diff-summary').textContent='选好两个版本后点「开始对比」';
    $('gd-diff-backdrop').hidden=false;viewer.hidden=false;
    document.querySelector('.app').inert=true;$('gd-diff-close').focus();}
  function closeGuideDiffModal(){const viewer=$('gd-diff-viewer');if(!viewer||viewer.hidden)return;viewer.hidden=true;$('gd-diff-backdrop').hidden=true;
    if($('login-view').hidden&&$('password-view').hidden&&$('guide-overlay').hidden)document.querySelector('.app').inert=false;
    state.tokens['guide-diff']=(state.tokens['guide-diff']||0)+1;}
  function gdScalePane(root){const dimensions=['font-size','line-height','margin-left','margin-right','margin-top','margin-bottom','text-indent','padding-left','padding-right','padding-top','padding-bottom'];
    root.querySelectorAll('[style]').forEach(node=>dimensions.forEach(property=>{const value=node.style.getPropertyValue(property).trim(),match=value.match(/^(-?\d+(?:\.\d+)?)(pt|px)$/);
      if(match)node.style.setProperty(property,`${Number((Number(match[1])*.9).toFixed(3))}${match[2]}`);}));}
  function gdSetPane(id,html){const pane=$(id);if(!pane)return;pane.innerHTML=html||'';gdScalePane(pane);
    pane.querySelectorAll('[data-diff-id]').forEach(mark=>{mark.tabIndex=0;});}
  function gdFilteredItems(d){return (d.items||[]).filter(item=>!d.filter||item.type===d.filter);}
  function gdRenderRail(d){const list=$('gd-diff-list');if(!list)return;const items=gdFilteredItems(d);
    list.innerHTML=items.length?items.map((item,index)=>{const kind=item.type==='modify'?'修改':item.type==='insert'?'插入':'删除';
      const preview=`${esc(item.location||'正文')} · ${esc((item.old_text||'').slice(0,46))}${item.new_text?' → '+esc((item.new_text||'').slice(0,46)):''}`;
      return `<div class="compare-diff-item ${index===d.cursor?'is-active':''}" data-gd-jump="${esc(item.id)}" role="button" tabindex="0"><span class="compare-diff-index">${index+1}</span><span class="compare-diff-kind is-${esc(item.type)}">${esc(kind)}</span><span class="compare-diff-preview">${preview}</span></div>`;}).join(''):'<p class="empty">当前筛选条件下没有差异。</p>';
    $('gd-diff-count-rail').textContent=String((d.items||[]).length);
    $('gd-diff-counter').textContent=`${d.cursor>=0?d.cursor+1:0} / ${items.length}`;}
  function gdRenderPanes(d){const td=d.td;if(!td)return;const word=d.view!=='classic';
    const layout=$('gd-diff-word-layout');
    $('gd-diff-sec-merged').hidden=!word;
    layout.classList.toggle('gd-classic',!word);
    layout.classList.toggle('is-sources-hidden', word && d.showSources===false);
    $('gd-diff-src-wrap').hidden=!word;
    // compare.css 的 data-view-mode=classic 会整体隐藏 .compare-word-view（真比对页用经典视图另件）——本弹窗双栏也走 word-view 容器，恒置 word。
    $('gd-diff-body').dataset.viewMode='word';
    document.querySelectorAll('[data-gd-view-mode]').forEach(btn=>btn.classList.toggle('is-active',(btn.dataset.gdViewMode==='word')===word));
    gdSetPane('gd-diff-merged-pane',td.merged_html);
    // 源文档两块：Word 视图右侧上下堆叠（默认显示,『显示源文档』可勾掉）；双栏对照撑满左右两大栏。
    if(!word||d.showSources!==false){gdSetPane('gd-diff-left-pane',td.left_html);gdSetPane('gd-diff-right-pane',td.right_html);}
    // 用户 2026-11-03：Word 视图三页一起滑——合并稿也入联动圈（ratio 闸刀同双栏）。
    if(!word||d.showSources!==false)bindGuideDiffScrollSync($('gd-diff-word-layout'));}
  function gdActivePane(d){return $(d.view==='classic'?'gd-diff-left-pane':'gd-diff-merged-pane');}
  function gdJump(d,item,index){if(!item)return;const items=gdFilteredItems(d);d.cursor=(typeof index==='number'&&index>=0)?index:items.indexOf(item);
    const pane=gdActivePane(d);
    pane?.querySelectorAll('.is-active').forEach(el=>el.classList.remove('is-active'));
    const mark=pane?pane.querySelector(`[data-diff-id="${CSS.escape(item.id)}"]`):null;
    if(mark){mark.classList.add('is-active');mark.scrollIntoView({block:'center'});}
    gdRenderRail(d);
    $('gd-diff-list')?.querySelector('.compare-diff-item.is-active')?.scrollIntoView({block:'nearest'});}
  function gdStep(dir){const d=state.guideDiff;if(!d)return;const items=gdFilteredItems(d);if(!items.length)return;
    d.cursor=d.cursor<0?(dir>0?0:items.length-1):((d.cursor+dir)%items.length+items.length)%items.length;
    gdJump(d,items[d.cursor],d.cursor);}
  async function startGuideDiff(){const d=state.guideDiff;if(!d||!d.from||!d.to||d.from===d.to){$('gd-diff-empty').hidden=false;$('gd-diff-empty').textContent='请选两个不同的版本再开始对比。';return;}
    const t=ticket('guide-diff');d.td=null;d.items=[];d.cursor=-1;
    $('gd-diff-body').hidden=true;$('gd-diff-empty').hidden=false;$('gd-diff-empty').textContent='正在计算差异…';
    try{const payload=await json(`/api/guides/${encodeURIComponent(d.to)}/text-diff?against=${encodeURIComponent(d.from)}`);if(!current(t))return;
      const td=payload.text_diff,s=td.summary;d.td=td;d.items=td.diffs||[];
      const fromItem=guideByName(d.from),toItem=guideByName(d.to);
      const sameCanon=td.from_version&&td.to_version&&td.from_version.canonical_sha256&&td.from_version.canonical_sha256===td.to_version.canonical_sha256;
      $('gd-diff-summary').textContent=sameCanon?'两个版本引用的是同一份档案，比对必然一致（内置各代共享冻结档案时属预期）':(td.identical?'两个版本的原文完全一致':`共 ${s.diffs} 处差异 · 修改 ${s.modify} · 新增 ${s.insert} · 删除 ${s.delete}`);
      $('gd-diff-merged-name').textContent=`${fromItem?fromItem.filename:''} → ${toItem?toItem.filename:''}`;
      $('gd-diff-left-name').textContent=fromItem?fromItem.filename:'';$('gd-diff-right-name').textContent=toItem?toItem.filename:'';
      $('gd-diff-empty').hidden=true;$('gd-diff-body').hidden=false;
      gdRenderPanes(d);gdRenderRail(d);}
    catch(e){if(!current(t))return;$('gd-diff-body').hidden=true;$('gd-diff-empty').hidden=false;
      $('gd-diff-empty').textContent=e&&e.code===404?'该版本的原文档案暂不可用，请换一个版本再试。':(e&&e.raw?`差异暂未算出来：${e.raw}`:'差异暂未算出来，请稍后重试。');}}
  // A8 指引版本比对：并排对照两栏滚动比例同步（CX 契约最短路径）。
  // rAF 闸刀 + syncTargets 回声抑制（160ms 无事件释放，防惯性滚动回环）+ 手势夺权。
  const guideDiffSyncState={targets:new Set(),frame:null,releaseTimer:undefined};
  function bindGuideDiffScrollSync(wrap){
    if(!wrap)return;
    const panes=[...wrap.querySelectorAll('.compare-pane')].filter(p=>p.clientHeight);
    if(panes.length<2)return;
    const sync=(source)=>{
      if(matchMedia('(max-width: 760px)').matches)return;
      if(guideDiffSyncState.targets.has(source)||guideDiffSyncState.frame!==null)return;
      guideDiffSyncState.frame=requestAnimationFrame(()=>{
        guideDiffSyncState.frame=null;
        const targets=panes.filter(p=>p!==source&&p.clientHeight);
        if(!targets.length)return;
        const sourceMax=Math.max(0,source.scrollHeight-source.clientHeight);
        const ratio=sourceMax?source.scrollTop/sourceMax:0;
        targets.forEach(target=>{guideDiffSyncState.targets.add(target);const targetMax=Math.max(0,target.scrollHeight-target.clientHeight);target.scrollTop=ratio*targetMax;});
        clearTimeout(guideDiffSyncState.releaseTimer);
        guideDiffSyncState.releaseTimer=setTimeout(()=>guideDiffSyncState.targets.clear(),160);
      });
    };
    const takeControl=(e)=>guideDiffSyncState.targets.delete(e.currentTarget);
    panes.forEach(pane=>{
      pane.addEventListener('scroll',()=>sync(pane),{passive:true});
      pane.addEventListener('wheel',takeControl,{passive:true});
      pane.addEventListener('pointerdown',takeControl,{passive:true});
      pane.addEventListener('touchstart',takeControl,{passive:true});
    });
  }
  async function enableGuide(id) {if(state.guideBusy)return;state.guideBusy=id;renderGuides();const t=ticket('guide-action'),item=guideByName(id);try{const payload=await json('/api/settings/guide',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({version_id:id})});if(!current(t))return;if(Array.isArray(payload.available))state.guides=payload.available;state.guideBusy=null;renderGuides();toast(`已启用指引：${item?item.filename:id}`);closeGuidePanel();await loadCapabilities();}
    catch(e){if(!current(t))return;state.guideBusy=null;renderGuides();errorNotice(e,'指引切换未完成：');}}
  async function resetToBuiltinGuide() {if(state.guideBusy)return;state.guideBusy='reset';renderGuides();const t=ticket('guide-action');try{const payload=await json('/api/settings/guide',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({version_id:null})});if(!current(t))return;if(Array.isArray(payload.available))state.guides=payload.available;state.guideBusy=null;renderGuides();toast('已恢复内置指引，之后创建的任务使用内置指引。');await loadCapabilities();}
    catch(e){if(!current(t))return;state.guideBusy=null;renderGuides();errorNotice(e,'恢复内置指引未完成：');}}
  async function reparseGuide(id) {if(state.guideBusy)return;state.guideBusy=id;renderGuides();const t=ticket('guide-action');try{const payload=await json(`/api/guides/${encodeURIComponent(id)}/parse`,{method:'POST'});if(!current(t))return;const version=payload&&payload.version;state.guideBusy=null;await loadGuides(true);toast(version&&version.id!==id?'已创建新版本（见列表顶部），原版本保持不变；解析完成后可启用。':'已提交重新解析，稍后查看刷新状态。');}
    catch(e){if(!current(t))return;state.guideBusy=null;renderGuides();errorNotice(e,'重新解析未完成：');}}
  // ── 指引页分区 tab（版本 / 对比与上传）──────────────────────────────────
  function renderGuideTabs(){const tab=state.guideTab||'versions';document.querySelectorAll('[data-guide-page-tab]').forEach(btn=>{const active=btn.dataset.guidePageTab===tab;btn.classList.toggle('is-active',active);btn.setAttribute('aria-selected',String(active));});document.querySelectorAll('[data-guide-pane]').forEach(pane=>{pane.hidden=pane.dataset.guidePane!==tab;});}
  function openGuideTab(tab){state.guideTab=tab;renderGuideTabs();}
  function downloadGuideSource(id) {const item=guideByName(id);if(!item||item.built_in)return;download(`/api/guides/${encodeURIComponent(id)}/source`,item.filename || `${id}.docx`);}
  async function uploadGuide() {const input=$('guide-file'),file=input&&input.files?input.files[0]:null,message=$('guide-upload-message');if(!file||state.guideUploading)return;
    if(!/\.docx$/i.test(file.name)){message.textContent='仅支持 DOCX 指引文件，请重新选择。';return;}
    const limit=state.cap&&state.cap.upload_limits?state.cap.upload_limits.max_file_bytes:0;if(limit&&file.size>limit){message.textContent=`文件超过单文件 ${size(limit)} 限制，请压缩后再上传。`;return;}
    const epoch=state.epoch;state.guideUploading=true;$('guide-upload-btn').disabled=true;const form=new FormData();form.append('file',file,file.name);message.textContent='正在上传指引原件…';
    try{const payload=await uploadRequest('/api/guides',form,(loaded,total)=>{if(identityCurrent(epoch))message.textContent=`正在上传指引原件 · ${Math.min(100,Math.round(100*loaded/total))}%`;});if(!identityCurrent(epoch))return;const version=payload&&payload.version;message.textContent=`已上传 ${version&&version.filename?version.filename:file.name}，等待解析（上传成功不代表解析完成）；解析成功并形成可执行指引卡后会自动成为之后任务的默认指引。`;input.value='';$('guide-file-name').textContent='尚未选择文件';toast('指引已上传，正在自动解析');await loadGuides();}
    catch(e){if(!identityCurrent(epoch)||e.name==='AbortError')return;message.textContent=e.code===415?'仅支持 DOCX 指引文件，请重新选择。':e.code===413?`文件超过接收限制${limit?`（单文件 ≤ ${size(limit)}）`:''}。`:e.message || '上传未完成，请稍后重试。';errorNotice(e,'指引上传失败：');}
    finally{if(identityCurrent(epoch)){state.guideUploading=false;$('guide-upload-btn').disabled=!(input.files&&input.files.length);}}}
  // ── 指引详情弹层（FL-D993：规则开关子页面与启停功能已删除，仅保留信息/概览/问题）──
  function openGuidePanel(id) {const item=guideByName(id);if(!item)return;const t=ticket('guide-detail');state.guideDetail={id};state.focusReturn=document.activeElement;$('guide-overlay-title').textContent=item.filename;$('guide-overlay-body').innerHTML='<div class="empty">正在读取指引详情…</div>';$('guide-overlay').hidden=false;document.querySelector('.app').inert=true;$('guide-overlay-close').focus();loadGuidePanel(item,t);}
  async function loadGuidePanel(item,t) {
    try{const data=await json(`/api/guides/${encodeURIComponent(item.id)}`);if(!current(t)||$('guide-overlay').hidden)return;
      renderGuidePanel(item,data);}
    catch(e){if(!current(t)||$('guide-overlay').hidden)return;$('guide-overlay-body').innerHTML='<div class="empty">指引详情暂无法读取，请关闭后重试。</div>';if(e.code!==404)errorNotice(e);}}
  const GUIDE_ISSUE_HINTS={
    GUIDE_SLOT_NOT_IN_TEXT:'核对新文中是否包含指引引用的占位标记；修正指引原文后重新解析（自动修复）。',
    GUIDE_GROUP_INVALID:'检查该规则的规则编号、操作与文本字段是否完整，修正后重新解析。',
    GUIDE_PARAGRAPH_RANGE_INVALID:'检查来源段落编号是否超出指引正文范围，修正后重新解析。',
    GUIDE_PARAGRAPH_ORDER:'来源段落编号需按升序且不重复，修正后重新解析。',
    GUIDE_GROUP_EMPTY:'该来源段落未生成有效规则，补充或调整来源编号后重新解析。'
  };
  function guideIssueHint(code){return GUIDE_ISSUE_HINTS[code]||'核对问题位置和指引原文；如为指引原件问题，修正后点击“重新解析”。';}
  // FL-D894：解析问题照常展示人读名称与位置，英文错误码收进折叠详情，不再裸显
  const GUIDE_ISSUE_LABELS={
    GUIDE_SLOT_NOT_IN_TEXT:'指引引用与原条款对不上',
    GUIDE_GROUP_INVALID:'规则数据不完整',
    GUIDE_PARAGRAPH_RANGE_INVALID:'段落编号超出指引正文范围',
    GUIDE_PARAGRAPH_ORDER:'段落编号顺序有误',
    GUIDE_GROUP_EMPTY:'该段落未生成有效规则',
    GUIDE_COVERAGE_GAP:'指引原文未覆盖的段落',
  };
  function guideIssueLabel(code){return GUIDE_ISSUE_LABELS[code]||'解析问题';}
  function guideIssueDetails(code,rule,detail,paragraphs=[],evidence='',open=false){
    const position=[rule?`规则 ${rule}`:'未提供规则编号',Array.isArray(paragraphs)&&paragraphs.length?`段落 ${paragraphs.join('、')}`:''].filter(Boolean).join(' · ');
    return `<li><details class="guide-issue" ${open?'open':''}><summary>${esc(guideIssueLabel(code))}${detail?` · ${esc(String(detail).slice(0,80))}`:''}</summary><dl class="guide-issue-grid"><dt>问题位置</dt><dd>${esc(position||'未提供')}</dd><dt>失败原因</dt><dd>${esc(detail||'未提供详细原因')}</dd><dt>修复建议</dt><dd>${esc(guideIssueHint(code))}</dd><dt>问题代码</dt><dd><code>${esc(code||'—')}</code></dd></dl>${evidence?`<details class="guide-quote"><summary>证据原文</summary><p>${esc(evidence)}</p></details>`:''}</details></li>`;
  }
  function guideIssuesHTML(issues,item) {const value=issues&&typeof issues==='object'?issues:{},errors=Array.isArray(value.errors)?value.errors:[],warnings=Array.isArray(value.warnings)?value.warnings:[],gaps=Array.isArray(value.coverage_gaps)?value.coverage_gaps:[],findings=value.verification&&Array.isArray(value.verification.findings)?value.verification.findings:[];let html='';
    if(value.error_code&&!errors.length)html+=`<p class="subnote">最近一次解析未通过：${esc(reasons[value.error_code]?reason(value.error_code):'解析未通过，请检查文件后重试')}${value.attempts?` · 已尝试 ${esc(String(value.attempts))} 次`:''}</p>`;
    if(errors.length)html+=`<h4 class="guide-issue-head">校验错误 · ${errors.length} 项</h4><ul class="guide-issues">${errors.map(entry=>guideIssueDetails(entry&&entry.code,entry&&entry.rule_id,entry&&entry.detail,[],'',true)).join('')}</ul>`;
    if(warnings.length)html+=`<h4 class="guide-issue-head">校验警告 · ${warnings.length} 项</h4><ul class="guide-issues">${warnings.map(entry=>guideIssueDetails(entry&&entry.code,entry&&entry.rule_id,entry&&entry.detail)).join('')}</ul>`;
    if(gaps.length)html+=`<h4 class="guide-issue-head">未覆盖段落 · ${gaps.length} 处</h4><ul class="guide-issues">${gaps.map(index=>guideIssueDetails('GUIDE_COVERAGE_GAP','', '该段未被任何规则引用', [index])).join('')}</ul>`;
    if(findings.length)html+=`<h4 class="guide-issue-head">独立核验发现 · ${findings.length} 项</h4><ul class="guide-issues">${findings.map(finding=>guideIssueDetails(finding&&finding.kind?finding.kind:'FINDING',finding&&finding.rule_id,finding&&finding.description,Array.isArray(finding&&finding.paragraphs)?finding.paragraphs:[],finding&&finding.evidence_quote,true)).join('')}</ul>`;
    if(!html)html='<p class="subnote">尚未解析，或解析未发现问题。</p>';
    if(value.clean===true)html+='<p class="subnote">最近一次解析已通过确定性校验与独立核验。</p>';
    if(item&&!item.built_in&&GUIDE_PARSEABLE.includes(item.status))html+=`<div class="guide-issue-actions"><button class="btn btn-sm btn-primary" type="button" data-guide-reparse="${esc(item.id)}">重新解析</button></div>`;
    return html;}
  function guideCardActionText(card){const t=String(card&&(card.action_type??card.action)||'');return {replace:'替换',delete:'删除',insert_before:'新增（条款前）',insert_after:'新增（条款后）'}[t]||esc(t||'—');}
  function guideCardRows(data){// 卡包数据源优先级：cards_overview（六字段）→ rules_overview 卡行兜底
    const cards=Array.isArray(data.cards_overview)?data.cards_overview:[];
    if(cards.length)return cards.map(card=>({id:card.card_id||'—',title:card.title||'—',applicability:(card.applicability||'').toString().trim()||'（无条件）',sections:Array.isArray(card.target_sections)&&card.target_sections.length?card.target_sections.join('、'):'—',action:guideCardActionText(card),actionText:typeof card.action_text==='string'?card.action_text.trim():'',source:Array.isArray(card.source_paragraphs)&&card.source_paragraphs.length?`来源段落 ${card.source_paragraphs.join('、')}`:''}));
    const legacy=Array.isArray(data.rules_overview)?data.rules_overview:[];
    return legacy.filter(rule=>rule&&rule.card_id).map(rule=>({id:rule.card_id,title:rule.title||'—',applicability:rule.applicability||'—',sections:rule.section_hint||'—',action:guideCardActionText(rule)+(Number.isFinite(rule.locator_quotes)?` · 引句 ${rule.locator_quotes} 条`:''),actionText:'',source:''}));}
  function renderGuidePanel(item,data) {const overview=Array.isArray(data.rules_overview)?data.rules_overview:[],issues=data.issues_detail||{};
    const cardMode=data.guide_schema==='guide_card_v1'||overview.some(rule=>rule&&rule.card_id);const cardRows=cardMode?guideCardRows(data):[];
    let html=`<div class="detail-section"><h3>指引信息</h3><dl class="detail-grid"><dt>状态</dt><dd>${badge(item.status, GUIDE_STATUSES[item.status])}</dd><dt>类型</dt><dd>${guideKind(item)}${guideCurrentFlag(item)}</dd><dt>规则条数</dt><dd>${item.groups} 条</dd><dt>创建时间</dt><dd>${esc(guideTime(item.created_at))}</dd><dt>更新时间</dt><dd>${esc(guideTime(item.updated_at))}</dd></dl><div class="detail-actions"><button class="btn btn-sm btn-primary" type="button" data-guide-enable="${esc(item.id)}" ${item.current||!GUIDE_ENABLEABLE.includes(item.status)?'disabled':''} title="${item.current?'该指引当前正在使用':GUIDE_ENABLEABLE.includes(item.status)?'新任务改用该指引':'解析完成后才能启用'}">启用</button><button class="btn btn-sm" type="button" data-guide-parse="${esc(item.id)}" ${item.built_in||!GUIDE_PARSEABLE.includes(item.status)?'disabled':''} title="${item.built_in?'内置指引无需重新解析':GUIDE_PARSEABLE.includes(item.status)?'重新解析该版本（产生新版本，原版本保留）':'当前状态不能重新解析'}">重新解析</button><button class="btn btn-sm" type="button" data-guide-source="${esc(item.id)}" ${item.built_in?'disabled':''} title="${item.built_in?'内置指引不提供原件下载':'下载上传的指引原件'}">下载原件</button></div></div>`;
    if(cardMode&&cardRows.length){
      html+=`<div class="detail-section" data-testid="guide-cards-table"><h3>指引卡 · ${cardRows.length} 张</h3><div class="table-wrap"><table class="table" style="min-width:640px"><thead><tr><th>卡号</th><th>标题</th><th>适用情形</th><th>目标章节</th><th>操作内容</th></tr></thead><tbody>${cardRows.map(card=>`<tr><td>${esc(card.id)}</td><td>${esc(card.title)}</td><td>${esc(card.applicability)}</td><td>${esc(card.sections)}</td><td class="guide-ops"><strong class="guide-ops-type">${card.action}</strong>${card.actionText?` ${esc(card.actionText.slice(0,96))}${card.actionText.length>96?'…':''}`:''}${card.source?`<span class="row-sub">${esc(card.source)}</span>`:''}</td></tr>`).join('')}</tbody></table></div></div>`;
    }else if(cardMode){
      html+='<div class="detail-section" data-testid="guide-cards-table"><h3>指引卡</h3><p class="subnote">暂无指引卡；解析完成后生成。</p></div>';
    }else{
      // 用户 2026-11-03 口径：不维护 guide-rules-v1 旧格式兼容渲染，
      // 历史旧版仅最小化提示，保证可打开不出错。
      html+='<div class="detail-section"><h3>规则概览</h3><p class="subnote">历史版本（旧格式）：仅保留版本记录与重新解析入口，不再展示旧格式规则明细。</p></div>';
    }
    html+=`<div class="detail-section"><h3>解析问题</h3>${guideIssuesHTML(issues,item)}</div>`;
    const target=$('guide-overlay-body');target.innerHTML=html;}
  function closeGuidePanel() {const overlay=$('guide-overlay');if(!overlay||overlay.hidden)return;overlay.hidden=true;if($('login-view').hidden&&$('password-view').hidden)document.querySelector('.app').inert=false;state.tokens['guide-detail']=(state.tokens['guide-detail'] || 0)+1;state.guideDetail=null;$('guide-overlay-body').replaceChildren();$('guide-overlay-title').textContent='';if(state.focusReturn){state.focusReturn.focus();state.focusReturn=null;}}
  document.addEventListener('click',e=>{const gdRowBtn=e.target.closest('[data-guide-diff]');if(gdRowBtn&&!gdRowBtn.disabled){openGuideDiffModal(gdRowBtn.dataset.guideDiff);return;}if(e.target.closest('#gd-diff-close')||e.target.id==='gd-diff-backdrop'){closeGuideDiffModal();return;}if(e.target.id==='gd-diff-start'){startGuideDiff();return;}if(e.target.id==='gd-diff-prev'){gdStep(-1);return;}if(e.target.id==='gd-diff-next'){gdStep(1);return;}const gdMode=e.target.closest('[data-gd-view-mode]');if(gdMode){const d=state.guideDiff;if(d&&d.td){d.view=gdMode.dataset.gdViewMode==='classic'?'classic':'word';gdRenderPanes(d);gdRenderRail(d);}return;}const gdJumpEl=e.target.closest('[data-gd-jump]');if(gdJumpEl){const d=state.guideDiff;if(d){const items=gdFilteredItems(d),idx=items.findIndex(x=>x.id===gdJumpEl.dataset.gdJump);if(idx>=0)gdJump(d,items[idx],idx);}return;}const gdMark=e.target.closest('#gd-diff-merged-pane [data-diff-id],#gd-diff-left-pane [data-diff-id],#gd-diff-right-pane [data-diff-id]');if(gdMark){const d=state.guideDiff;if(d){const items=gdFilteredItems(d),idx=items.findIndex(x=>x.id===gdMark.dataset.diffId);if(idx>=0)gdJump(d,items[idx],idx);}return;}const retryBtn=e.target.closest('[data-doc-retry]');if(retryBtn){if(retryBtn.disabled)return;retryFailedDocument(retryBtn.dataset.docRetry,retryBtn);return;}const pageTab=e.target.closest('[data-guide-page-tab]');if(pageTab){openGuideTab(pageTab.dataset.guidePageTab);return;}const bindingAction=(e.target.closest('[data-action]')||{}).dataset?.action;if(bindingAction==='feishu-oauth-start'){startFeishuOAuth();return;}const crumb=e.target.closest('[data-crumb]');if(crumb){e.preventDefault();go(crumb.dataset.crumb,crumb.dataset.crumbId?{id:crumb.dataset.crumbId}:{});return;}const nav=e.target.closest('[data-nav]');if(nav){e.preventDefault();if(nav.dataset.nav==='import'&&(state.recover||!state.imports.length))newTask();else go(nav.dataset.nav);return;}const reviewAction=(e.target.closest('[data-action]')||{}).dataset?.action;if(reviewAction==='open-review'){openReview();return;}if(reviewAction==='accept-all'){generateSelected('accept');return;}if(reviewAction==='generate-selected'){generateSelected();return;}if(reviewAction==='review-close'){closeReview();return;}if(reviewAction==='review-accept-all'){setAllRevisions('accept');return;}if(reviewAction==='review-reject-all'){setAllRevisions('reject');return;}if(reviewAction==='review-prev'){switchReview(-1);return;}if(reviewAction==='review-next'){switchReview(1);return;}if(reviewAction==='download-selected'){const d=state.detail;if(d&&d.downloads&&d.downloads.selected_final)download(d.downloads.selected_final,`${d.name.replace(/\.docx$/i,'')}_selected_final.docx`);return;}const revItem=e.target.closest('[data-rev-item]');if(revItem){if(!e.target.closest('input,label'))focusRevision(Number(revItem.dataset.revItem));return;}const revNode=e.target.closest('#review-doc [data-rev]');if(revNode){if(!e.target.closest('a')){const entry=state.review?.revisions.find(r=>(r.revision_ids||[r.del_id,r.ins_id??Number(r.del_id)+1]).some(id=>String(id)===revNode.dataset.rev));if(entry)focusRevision(entry.del_id);}return;}const task=e.target.closest('[data-task]');if(task){selectTask(task.dataset.task);return;}const userToggle=e.target.closest('[data-user-toggle]');if(userToggle){toggleUser(userToggle.dataset.userToggle,userToggle.dataset.userDisabled!=='1');return;}const detail=e.target.closest('[data-detail]');if(detail){const [name,index]=detail.dataset.detail.split(':');showDetail(state.taskDocs[Number(index)]);return;}const replace=e.target.closest('[data-replace]');if(replace&&!state.uploading){state.replaceTarget=replace.dataset.replace;$('replace-picker').click();return;}const remove=e.target.closest('[data-remove]');if(remove&&!state.uploading){state.imports=state.imports.filter(f=>f.id!==remove.dataset.remove);state.createKey=null;renderImport();return;}const clearOne=e.target.closest('[data-clear-filter]');if(clearOne){const [scope,key]=clearOne.dataset.clearFilter.split(':');clearFilter(scope,key);return;}const clearAll=e.target.closest('[data-clear-filters]');if(clearAll){clearAllFilters(clearAll.dataset.clearFilters);return;}const page=e.target.closest('[data-page]');if(page){const name=page.dataset.page;state[`${name}Page`]+=page.dataset.dir==='next'?1:-1;if(name==='import')renderImport();else if(name==='task')loadTasks();else loadDocuments();return;}const dl=e.target.closest('[data-download]');if(dl&&state.detail){const kind=dl.dataset.download;const ext=kind.startsWith('report_')?(kind==='report_json'?'json':'md'):'docx';const label=isDirectDoc(state.detail)?{final:'最终版（全部修订已定案）',redline:'带痕版（保留全部修订标记）',selected_final:'选择版（按您的接受拒绝）',selected_redline:'选择版（带痕）'}[kind]:{final:'最终版',selected_final:'最终版（按人工选择）',redline:'修订版（引擎全量痕迹）',selected_redline:'修订版（仅人工接受）',working_final:'工作文件（供复核）',working_redline:'工作文件（供复核）修订痕迹'}[kind];download(state.detail.downloads[kind],`${state.detail.name.replace(/\.docx$/i,'')}${label?`_${label}`:''}.${ext}`);return;}const guideEnable=e.target.closest('[data-guide-enable]');if(guideEnable){enableGuide(guideEnable.dataset.guideEnable);return;}const guideParse=e.target.closest('[data-guide-parse]');if(guideParse){reparseGuide(guideParse.dataset.guideParse);return;}const guideReparse=e.target.closest('[data-guide-reparse]');if(guideReparse){closeGuidePanel();reparseGuide(guideReparse.dataset.guideReparse);return;}const guideIssues=e.target.closest('[data-guide-issues]');if(guideIssues){openGuidePanel(guideIssues.dataset.guideIssues);return;}const guideSource=e.target.closest('[data-guide-source]');if(guideSource){downloadGuideSource(guideSource.dataset.guideSource);return;}const action=e.target.closest('[data-action]')?.dataset.action;if(!action)return;switch(action){case 'open-password':openPasswordDialog();break;case 'help-open':openHelp();break;case 'help-close':closeHelp();break;case 'notifications':{const panel=$('notification-panel');panel.hidden=!panel.hidden;$('notification-toggle').setAttribute('aria-expanded',String(!panel.hidden));if(!panel.hidden){notifications.forEach(n=>n.read=true);renderNotifications();}break;}case 'download-all':if(!state.task){notify('请先选择任务。',true);break;}// FL-D1041：改 aria-disabled 后 click 可达——禁用态点击给学生同样可理的提醒。
      if(document.querySelector('[data-action="download-all"]')?.getAttribute('aria-disabled')==='true'){notify('该任务尚无可下载的合同结果，请等待处理完成或先在“任务详情”确认文件是否已生成。',true);break;}download(`${pathTask()}/download/all`,`${state.task.name}_全部结果.zip`);break;case 'new-task':newTask();break;case 'cancel-recover':if(state.uploading)break;state.importSession++;state.tokens.recovery=(state.tokens.recovery||0)+1;state.recover=null;state.imports=[];state.createKey=null;state.importPage=1;$('task-name').value='';resetImportStages();renderImport();go('task');break;case 'choose-files':$('file-picker').click();break;case 'choose-folder':$('folder-picker').click();break;case 'clear-import':if(!state.uploading){state.imports=[];state.createKey=null;state.importPage=1;state.uploadProgress=null;state.replaceTarget=null;resetImportStages(state.recover?(state.task?.id===state.recover.id?state.task:state.recover):null);renderImport();}break;case 'submit':submit();break;case 'dismiss-guide':{state.guideDismissed=true;try{localStorage.setItem(`fundlex-guide-dismissed:${localStorage.getItem('fundlex-dev-user')||'user'}`,'1');}catch{}$('first-run-guide').setAttribute('hidden','');break;}case 'refresh':refresh();break;case 'recover':recover();break;case 'toggle-pause':togglePause();break;case 'download-summary':if(state.task)download(state.task.summary_url,`${state.task.name}_结果总览.md`);else notice('请先选择任务。',true);break;case 'export-results':exportResults();break;case 'export-pending':exportPending();break;case 'users-refresh':loadUsers();break;case 'user-create':createUser();break;case 'model-settings-save':saveModelSettings(e.target.closest('[data-action="model-settings-save"]')?.dataset.modelSave||null);break;case 'guide-refresh':loadGuides();break;case 'guide-reset':resetToBuiltinGuide();break;case 'guide-choose':$('guide-file').click();break;case 'guide-upload':uploadGuide();break;}});
  for(const id of ['file-picker','folder-picker'])$(id).addEventListener('change',e=>{addFiles([...e.target.files]);e.target.value='';});$('replace-picker').addEventListener('change',e=>{const file=e.target.files&&e.target.files[0];const id=state.replaceTarget;state.replaceTarget=null;e.target.value='';if(file&&id)replaceFile(id,file);});const drop=$('dropzone');drop.addEventListener('dragover',e=>{e.preventDefault();if(!state.uploading)drop.classList.add('dragging');});drop.addEventListener('dragleave',()=>drop.classList.remove('dragging'));drop.addEventListener('drop',e=>{e.preventDefault();drop.classList.remove('dragging');addFiles([...e.dataTransfer.files]);});
  const debounces={};function changed(name){state[`${name}Page`]=1;if(name==='import')renderImport();else if(name==='task')loadTasks();else loadDocuments();}
  for(const name of ['task','import','doc'])$(`${name}-search`).addEventListener('input',()=>{clearTimeout(debounces[name]);state.tokens[name==='doc'?'doc':name==='task'?'tasks':name]=(state.tokens[name==='doc'?'doc':name==='task'?'tasks':name] || 0)+1;debounces[name]=setTimeout(()=>changed(name),250);});
  for(const [name,ids] of [['task',['task-filter','task-guide-filter','task-sort']],['import',['import-filter']],['doc',['doc-upload-filter','doc-qualification-filter','doc-completeness-filter','doc-status-filter','doc-reason-filter','doc-sort']]])for(const id of ids)$(id).addEventListener('change',()=>changed(name));
  for(const id of ['task-select'])$(id).addEventListener('change',e=>selectTask(e.target.value,false));
  document.addEventListener('change',e=>{if(e.target.id==='model-review-inherits'){const fields=$('model-review-fields');if(fields)fields.hidden=e.target.checked;return;}if(e.target.id==='import-mode'){state.importMode=e.target.value;renderImport();return;}const revToggle=e.target.dataset.revToggle;if(revToggle!==undefined&&state.review){setRevision(Number(revToggle),e.target.checked?'accept':'reject');return;}const name=e.target.dataset.pagesize;if(name){state[`${name}Size`]=Number(e.target.value);changed(name);}});$('dev-user').addEventListener('input',identityChanged);$('task-name').addEventListener('input',()=>{state.createKey=null;if(!$('task-name-error').hidden)nameError(true);});$('detail-body').addEventListener('click',e=>{const quote=e.target.closest('.evidence.quote');if(quote&&!e.target.closest('a,button'))quote.classList.toggle('expanded');});function closeContractDetail(){closeDetail();if(state.view==='document')go('task',{id:state.selected});}$('close-detail').addEventListener('click',closeContractDetail);$('detail-overlay').addEventListener('click',e=>{if(e.target===$('detail-overlay'))closeContractDetail();});document.addEventListener('keydown',e=>{if(e.key==='Escape'&&state.view==='document'&&!$('detail-overlay').hidden)closeContractDetail();});$('guide-file').addEventListener('change',e=>{const file=e.target.files?e.target.files[0]:null;$('guide-file-name').textContent=file?`已选择：${file.name}`:'尚未选择文件';$('guide-upload-btn').disabled=!file||state.guideUploading;});$('guide-overlay-close').addEventListener('click',closeGuidePanel);$('guide-overlay').addEventListener('click',e=>{if(e.target===$('guide-overlay'))closeGuidePanel();});$('help-close').addEventListener('click',closeHelp);$('help-overlay').addEventListener('click',e=>{if(e.target===$('help-overlay'))closeHelp();});document.addEventListener('keydown',e=>{if(!$('help-overlay').hidden&&e.key==='Escape'){closeHelp();}});document.addEventListener('keydown',e=>{if($('guide-overlay').hidden)return;if(e.key==='Escape'){closeGuidePanel();return;}if(e.key==='Tab'){const nodes=[...$('guide-overlay').querySelectorAll('button,summary,a[href],input,select')].filter(n=>!n.disabled&&n.offsetParent!==null),first=nodes[0],last=nodes.at(-1);if(!first)return;if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}});document.addEventListener('keydown',e=>{if(!state.review||$('detail-overlay').hidden||e.defaultPrevented||e.isComposing||e.ctrlKey||e.metaKey||e.altKey)return;const tag=(e.target&&e.target.tagName||'').toLowerCase();if((tag==='input'&&e.target.type!=='checkbox')||tag==='textarea'||tag==='select'||(e.target&&e.target.isContentEditable)||e.target?.closest?.('[role="separator"]'))return;const key=String(e.key||'').toLowerCase();if(key!=='a'&&key!=='r')return;const review=state.review;if(!review.revisions.length)return;const current=review.revisions.find(r=>String(r.del_id)===String(review.active))||review.revisions[0];e.preventDefault();setRevision(current.del_id,key==='a'?'accept':'reject');focusRevision(current.del_id);});document.addEventListener('keydown',e=>{if($('detail-overlay').hidden)return;if(e.key==='Escape'){closeDetail();return;}if(e.key==='Tab'){const nodes=[...$('detail-overlay').querySelectorAll('button,summary,a[href],input,select')].filter(n=>!n.disabled&&n.offsetParent!==null),first=nodes[0],last=nodes.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}});
  $('document-host').append($('detail-overlay'));
  $('detail-overlay').classList.add('inline-contract-detail');
  // A9-F04：所有分栏共用一个 resize 监听；句柄失连（面板重渲染）时自动移除，避免监听器泄漏。
  const columnSplitterRegistry = new Set();
  let columnSplitterResizeBound = false;
  function bindColumnSplitterResize() {
    if (columnSplitterResizeBound) return;
    columnSplitterResizeBound = true;
    let resizeFrame = null;
    window.addEventListener('resize', () => {
      if (resizeFrame) return;
      resizeFrame = requestAnimationFrame(() => {
        resizeFrame = null;
        for (const entry of [...columnSplitterRegistry]) {
          if (!entry.handle.isConnected) { columnSplitterRegistry.delete(entry); continue; }
          entry.apply(entry.current, false);
        }
      });
    });
  }
  function bindColumnSplitter(handle, container, target, options = {}) {
    if (!handle || !container || !target) return null;
    const opts = {
      key: '', variable: '--column-width', min: 220, max: 680,
      minOther: 420, fallback: 320, side: 'right',
      disabled: () => false, onChange: null, ...options,
    };
    const targetElement = () => typeof target === 'function' ? target() : target;
    const maxWidth = () => {
      // The reader dialog exists but is hidden on initial binding; do not
      // collapse a fallback width to the minimum while clientWidth is zero.
      if (!container.clientWidth) return opts.max;
      return Math.max(opts.min, Math.min(opts.max, container.clientWidth - opts.minOther));
    };
    let current = opts.fallback;
    if (opts.key) {
      try {
        const stored = Number(localStorage.getItem(opts.key));
        if (Number.isFinite(stored) && stored > 0) current = stored;
      } catch {}
    }
    const apply = (value, persist = false) => {
      const next = Math.max(opts.min, Math.min(maxWidth(), Math.round(Number(value) || opts.fallback)));
      const changed = next !== current;
      current = next;
      container.style.setProperty(opts.variable, `${next}px`);
      handle.setAttribute('aria-valuenow', String(next));
      handle.setAttribute('aria-valuemin', String(opts.min));
      handle.setAttribute('aria-valuemax', String(Math.round(maxWidth())));
      handle.setAttribute('aria-valuetext', `${next} 像素`);
      if (persist && opts.key) {
        try { localStorage.setItem(opts.key, String(next)); } catch {}
      }
      if (changed && opts.onChange) opts.onChange(next);
      return next;
    };
    apply(current, false);
    let dragging = false, startX = 0, startWidth = 0, resizeFrame = null;
    const direction = () => typeof opts.side === 'function' ? opts.side() : opts.side;
    const onMove = event => {
      if (!dragging) return;
      const delta = (event.clientX - startX) * (direction() === 'left' ? 1 : -1);
      apply(startWidth + delta);
    };
    const onUp = () => {
      if (!dragging) return;
      dragging = false;
      handle.classList.remove('is-dragging');
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onUp);
      apply(current, true);
      // Drag end is where heavy geometry work (re-measure, cross-pane
      // realign) belongs; firing it per pointermove made drags stutter.
      if (typeof opts.onEnd === 'function') opts.onEnd(current);
    };
    handle.addEventListener('pointerdown', event => {
      if (event.button !== 0 || opts.disabled()) return;
      const element = targetElement();
      if (!element) return;
      event.preventDefault();
      dragging = true;
      startX = event.clientX;
      startWidth = element.getBoundingClientRect().width;
      handle.classList.add('is-dragging');
      handle.setPointerCapture?.(event.pointerId);
      window.addEventListener('pointermove', onMove);
      window.addEventListener('pointerup', onUp);
      window.addEventListener('pointercancel', onUp);
    });
    handle.addEventListener('dblclick', () => apply(opts.fallback, true));
    handle.addEventListener('keydown', event => {
      if (opts.disabled()) return;
      const dir = direction(), step = event.shiftKey ? 60 : 20;
      let next = current;
      if (event.key === 'ArrowLeft') next += dir === 'right' ? step : -step;
      else if (event.key === 'ArrowRight') next += dir === 'right' ? -step : step;
      else if (event.key === 'Home') next = opts.min;
      else if (event.key === 'End') next = maxWidth();
      else if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault(); apply(opts.fallback, true); return;
      } else return;
      event.preventDefault(); apply(next, true);
    });
    const entry = {handle, apply, get current() { return current; }};
    columnSplitterRegistry.add(entry);
    bindColumnSplitterResize();
    return {apply, get width() { return current; }, dispose() { columnSplitterRegistry.delete(entry); }};
  }
  window.FundLexColumnSplitter = bindColumnSplitter;
  window.FundLexWorkbench={json,esc,toast,go,navigate:go,download,appPath,setObjectTitle,route:()=>({...state.route}),ready:()=>!!state.cap,epoch:()=>state.epoch,view:()=>state.view,authenticated:()=>state.auth.mode!=='password'||!!state.auth.token};
  window.addEventListener('hashchange',()=>{if(location.hash!==state.routeHash){const route=routeFromHash();go(route.view,Object.fromEntries(Object.entries(route).filter(([key])=>key!=='view')));}});document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&document.title!==BASE_TITLE)document.title=BASE_TITLE;});try{$('dev-user').value=localStorage.getItem('fundlex-dev-user') || 'local-user';}catch{$('dev-user').value='local-user';}state.auth.token=storedToken();state.auth.user=storedUser();$('login-form').addEventListener('submit',submitLogin);$('register-form').addEventListener('submit',submitRegister);$('register-link').addEventListener('click',()=>switchAuthMode('register'));$('register-back').addEventListener('click',()=>switchAuthMode('login'));$('logout-btn').addEventListener('click',logout);$('password-btn').addEventListener('click',openPasswordDialog);$('pwd-cancel').addEventListener('click',closePasswordDialog);$('password-form').addEventListener('submit',submitPasswordChange);$('password-view').addEventListener('click',e=>{if(e.target===$('password-view'))closePasswordDialog();});document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('password-view').hidden)closePasswordDialog();});renderAuthUI();renderTask();renderImport();go(location.hash.slice(1));refresh(true).then(()=>{monitorTasks();openDeepLinkedTask();});setInterval(()=>{if(state.cap&&!state.refreshBusy&&document.visibilityState==='visible'&&(state.view==='overview'||(state.task&&['uploading','queued','running','paused'].includes(state.task.status)))){state.refreshBusy=true;refresh(true).finally(()=>{state.refreshBusy=false;});}},10000);setInterval(()=>{if(document.visibilityState==='visible')monitorTasks();},15000);document.addEventListener('keydown',e=>{if(e.key==='Escape'){$('notification-panel').hidden=true;$('notification-toggle').setAttribute('aria-expanded','false');}});document.addEventListener('click',e=>{if(!e.target.closest('.notification-center')){$('notification-panel').hidden=true;$('notification-toggle').setAttribute('aria-expanded','false');}});
})();
