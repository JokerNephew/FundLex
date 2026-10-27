/* V1 guide-generation business space. Authentication and routing belong to app.js. */
(() => {
  "use strict";
  const API = "/api/guide-generation";
  const CORPUS_LIMIT_MAX = 10000; // PublicPipelineConfig.corpus_limit upper bound.
  const TABS = { overview: "总览", guide: "候选指引", requirements: "法规依据", issues: "待处理问题", versions: "版本与导出" };
  const STAGES = {
    INGEST_REGULATION: "法规读取", EXTRACT_REQUIREMENTS: "要求提取", VERIFY_REQUIREMENTS: "要求核对",
    BUILD_CORPUS_SNAPSHOT: "参考合同快照", DISCOVERY_REQUIREMENT_RETRIEVAL: "合同影响检索",
    DISCOVERY_CONTRACT_SWEEP: "合同影响扫描", ADJUDICATE_IMPACTS: "影响判定",
    BUILD_LOCAL_GUIDE_CANDIDATES: "指引起草", MERGE_AND_GENERALIZE: "指引归并",
    GUIDE_QUALITY_REVIEW: "质量核验", GUIDE_REPAIR: "指引修复", SEMANTIC_COVERAGE: "覆盖核验",
    RESIDUAL_MINING: "查漏补缺", FINALIZE_GUIDE: "候选输出", BUILD_EVIDENCE: "证据与报告",
  };
  const LABELS = {
    queued: "排队中", running: "处理中", paused: "已暂停", complete: "生成结束", completed: "生成结束",
    complete_with_unresolved: "生成结束 · 仍有问题", failed: "处理失败", error: "异常", cancelled: "已取消",
    draft: "草稿", candidate: "AI 候选", candidate_ready: "候选待审阅", candidate_with_findings: "候选存在待处理问题",
    human_draft: "人工草稿 · 待审阅", approved: "候选已批准", published: "候选已发布",
    not_run: "未核验", not_requested: "未请求", pending: "待处理", pass: "通过", passed: "通过",
    fail: "未通过", pass_with_findings: "存在问题", human_review_pending: "人工修改后待审阅",
    covered: "已覆盖", disposed: "已有去向", gap: "覆盖缺口", uncertain: "尚不确定", unresolved: "尚未解决",
    not_applicable: "不适用", false_positive: "非真实影响", affected: "有影响", not_affected: "无影响",
    definite: "明确影响", possible: "可能影响", unlikely: "影响可能性低", modify_contract: "需修改合同",
    no_contract_change: "无需修改合同", open: "待处理", resolved: "已解决", critical: "关键问题", high: "高风险",
    medium: "一般问题", major: "重要问题", minor: "一般问题", low: "提示", info: "信息", model_drafted: "模型起草",
    regulation_verbatim: "法规原文", contract_pattern_adapted: "参照合同改写",
    requirement: "法规要求", impact: "合同影响", contract_requirement: "合同 × 法规要求",
    succeeded: "完成", skipped: "已跳过", budget_exhausted: "预算已用尽", saturated: "本轮策略下未发现新缺口",
    new_uncovered: "发现新缺口", clean: "本轮未发现新缺口", max_rounds_reached: "已达到补漏轮次上限",
    ambiguous: "适用性不明确", not_covered: "未覆盖", model_error: "模型调用异常",
  };
  const CHECKS = {
    all_requirements_have_evidence: "法规要求均有原文证据", all_requirements_dispositioned: "法规要求均有处理去向",
    all_guide_items_have_requirement: "指引条目均关联法规要求", all_guide_items_have_impact: "指引条目均关联合同影响",
    all_guide_items_have_new_text_origin: "建议新文均标注来源", requirement_coverage_complete: "法规要求无覆盖缺口",
    impact_coverage_complete: "合同影响无未解决项", latest_contract_coverage_complete: "最新合同无不确定项",
    residual_saturated: "补漏达到当前策略的停止条件",
  };
  const FIELDS = {
    title: "条目标题", business_requirement: "业务要求", instruction: "修改指令", applicability: "适用范围",
    conditions: "适用条件（每行一条）", exceptions: "例外（每行一条）", old_text_patterns: "旧文模式（每行一条）",
    new_text: "建议合同新文", new_text_origin: "新文来源",
  };
  const LIST_FIELDS = new Set(["conditions", "exceptions", "old_text_patterns"]);
  const DOWNLOADS = {
    guide: ["当前候选 DOCX", "generated_guide.docx"], guide_ai: ["AI 原版 DOCX", "generated_guide_ai.docx"],
    evidence_json: ["完整证据 JSON", "guide_generation_evidence.json"], evidence_html: ["核验报告 HTML", "guide_generation_report.html"],
    engine_json: ["引擎兼容报告 JSON", "engine_compatibility_report.json"], engine_html: ["引擎兼容报告 HTML", "engine_compatibility_report.html"],
  };
  const state = {
    serial: 0, active: false, route: null, timer: null, runs: [], query: "", status: "", listPage: 1, listMeta: null,
    detail: null, guide: null, candidate: null, requirements: [], drafts: new Map(), selected: "",
    file: null, busy: false, impactsSerial: 0, impactPage: 1, impactRequirement: "", impactStatus: "",
    openEpoch: null, authValue: false,
  };
  const workbench = () => window.FundLexWorkbench;
  const root = () => document.getElementById("gg-root");
  const $ = (id) => document.getElementById(id);
  const esc = (value) => workbench().esc(String(value ?? ""));
  const label = (value) => LABELS[value] || value || "尚无结论";
  const text = (value) => Array.isArray(value) ? value.join("\n") : String(value ?? "");
  const complete = () => ["complete", "completed", "complete_with_unresolved"].includes(state.detail?.status);
  const dirty = () => state.drafts.size > 0 || Boolean(state.file) || state.busy;
  const stamp = () => ({ serial: state.serial, epoch: workbench().epoch() });
  const alive = (ctx) => state.active && ctx.serial === state.serial && ctx.epoch === workbench()?.epoch();
  const runPath = (suffix = "") => `${API}/runs/${encodeURIComponent(state.route.id)}${suffix}`;
  const stage = (value) => STAGES[value] || ({ queued: "等待处理", QUEUED: "等待处理", failed: "处理失败", FAILED: "处理失败", PAUSED: "已暂停" }[value]) || "等待阶段更新";
  const date = (value) => value ? new Date(typeof value === "number" ? value * 1000 : value).toLocaleString("zh-CN") : "—";
  const runProblem = (code) => {
    if (!code) return "";
    const message = code.includes("BUDGET") ? "本次调用或费用已达到上限，任务未完成。请核对预算后再继续，不要重复创建任务。"
      : code.startsWith("MODEL_") ? "模型服务暂时无法完成请求，任务未完成。请核对服务可用性、权限或额度后再继续，已完成阶段会保留。"
      : "任务未能完成。请保留任务编号并查看原因，不要把当前文件当作已核验指引。";
    return note(message, "error") + `<details class="gg-technical"><summary>查看技术原因</summary><code>${esc(code)}</code></details>`;
  };
  const button = (action, title, extra = "") => `<button type="button" class="btn ${extra}" data-gg-action="${action}">${title}</button>`;
  const badge = (value) => {
    const tone = ["failed", "error", "fail", "critical", "gap", "unresolved"].includes(value) ? "error"
      : ["candidate_with_findings", "human_draft", "human_review_pending", "complete_with_unresolved", "pass_with_findings", "uncertain", "possible"].includes(value) ? "warning"
        : ["approved", "published", "pass", "passed", "covered", "resolved"].includes(value) ? "success" : "neutral";
    return `<span class="gg-badge gg-${tone}">${esc(label(value))}</span>`;
  };
  const note = (message, tone = "notice") => `<div class="gg-note gg-${tone}">${esc(message)}</div>`;
  const empty = (message) => `<div class="gg-empty" role="status">${esc(message)}</div>`;
  const loading = (message = "正在读取…") => `<div class="gg-empty" role="status" aria-live="polite">${esc(message)}</div>`;
  const quote = (value, title = "原文证据") => value ? `<blockquote class="gg-quote"><small>${esc(title)}</small>${esc(value)}</blockquote>` : '<p class="gg-muted">尚无原文证据。</p>';
  const card = (title, body) => `<section class="card gg-card"><h2>${esc(title)}</h2>${body}</section>`;
  const metric = (title, value, hint = "") => `<div class="gg-metric"><span>${esc(title)}</span><strong>${esc(value ?? "—")}</strong><small>${esc(hint)}</small></div>`;
  function errorMessage(error) {
    const message = String(error?.message || "读取失败，请稍后重试。");
    // The shared helper preserves machine-readable errors in .raw/.code.
    const context = `${error?.raw || ""} ${error?.code || ""} ${message}`;
    if (/CANDIDATE_VERSION_CONFLICT|candidate version changed|current version/i.test(context)) return "当前版本已变化。你的未保存编辑仍保留；请复制需要的内容，再放弃编辑并刷新后合并。";
    if (/PUBLISHED_IMMUTABLE/i.test(context)) return "该候选已发布，不能改写。你的编辑尚未保存。";
    if (/GUIDE_RETRY_LIMIT/i.test(context)) return "已达到处理尝试次数上限，不能继续重试。请保留任务编号联系支持。";
    if (/GUIDE_RUN_NOT_RESUMABLE/i.test(context)) return "任务状态已变化，目前不能继续处理。请刷新核对；不会自动重试。";
    if (/401|登录|auth/i.test(context)) return "登录状态已失效，请通过工作台重新登录。";
    if (/403/i.test(context)) return "当前账号无权执行此操作，请核对工作台身份。";
    if (/404|not found/i.test(context)) return "任务或产物尚不可用，或当前账号无权访问。";
    if (/REGULATION_FILE_LIMIT/i.test(context)) return "法规文件不能超过 80 MB。";
    if (/RUN_NOT_COMPLETE/i.test(context)) return "任务尚未结束，暂不能执行该操作。";
    return message;
  }
  async function request(path, options, ctx) {
    if (!alive(ctx)) throw new Error("GG_STALE");
    const result = await workbench().json(path, options || {});
    if (!alive(ctx)) throw new Error("GG_STALE");
    return result;
  }
  function showError(target, error, ctx) {
    if (!alive(ctx) || !target) return;
    target.innerHTML = `<div class="gg-note gg-error" role="alert">${esc(errorMessage(error))}</div><div class="gg-actions">${button("refresh", "重试")}${state.route?.mode === "detail" ? button("list", "返回任务列表") : ""}</div>`;
  }
  function notify(error, ctx) {
    if (alive(ctx)) workbench().toast(errorMessage(error));
  }
  function navigate(options) {
    workbench().navigate("generation", { page: String(state.listPage), q: state.query, status: state.status, ...options });
  }
  function routePage(value) { return /^\d+$/.test(String(value)) && Number.isSafeInteger(Number(value)) && Number(value) > 0 ? Number(value) : 1; }
  function heading(title, subtitle, actions = "") {
    return `<header class="gg-heading"><div><h1 class="object-title">${esc(title)}</h1><p class="gg-muted">${esc(subtitle)}</p></div><div class="gg-actions">${actions}</div></header>`;
  }

  async function open(route = {}) {
    clearTimeout(state.timer);
    state.serial++;
    state.active = true;
    if (state.route?.id !== (route.id || "")) {
      state.selected = "";
      state.impactPage = 1;
      state.impactRequirement = "";
      state.impactStatus = "";
    }
    state.listPage = route.page == null ? state.listPage : routePage(route.page);
    state.query = String(route.q ?? state.query);
    state.status = String(route.status ?? state.status);
    state.route = { mode: ["list", "new", "detail"].includes(route.mode) ? route.mode : "list", id: route.id || "", tab: TABS[route.tab] ? route.tab : "overview", page: String(state.listPage), q: state.query, status: state.status };
    state.detail = null;
    state.guide = null;
    state.candidate = null;
    state.requirements = [];
    state.drafts.clear();
    state.file = null;
    state.busy = false;
    const target = root();
    if (!target || !workbench()) return;
    state.openEpoch = workbench().epoch();
    state.authValue = workbench().authenticated();
    target.className = "gg-workspace";
    if (!workbench().authenticated()) {
      target.innerHTML = empty("请先通过工作台登录，再使用指引生成。");
      return;
    }
    const ctx = stamp();
    if (state.route.mode === "new") return renderNew(ctx);
    if (state.route.mode === "detail" && state.route.id) return loadDetail(ctx);
    state.route.mode = "list";
    return loadList(ctx);
  }

  async function loadList(ctx) {
    root().innerHTML = `<section class="card gg-card"><form id="gg-filter" class="gg-toolbar"><label class="gg-search">搜索任务<input id="gg-query" type="search" placeholder="任务名或法规文件名" value="${esc(state.query)}"></label><label>任务状态<select id="gg-status"><option value="">全部状态</option>${["queued", "running", "paused", "failed", "complete", "complete_with_unresolved"].map((value) => `<option value="${value}" ${state.status === value ? "selected" : ""}>${esc(label(value))}</option>`).join("")}</select></label><button class="btn" type="submit">筛选</button>${button("refresh", "刷新")}${button("new", "＋ 新建生成任务", "btn-primary page-primary")}</form><p class="gg-muted" id="gg-list-scope">正在读取任务…</p><div id="gg-list-results">${loading()}</div><div id="gg-list-pages" class="gg-pagination"></div></section>`;
    try {
      const params = new URLSearchParams({ page: String(state.listPage), page_size: "20", q: state.query, status: state.status });
      let data = await request(`${API}/runs?${params}`, {}, ctx);
      const paged = Array.isArray(data.items) && Number.isSafeInteger(data.total) && data.total >= 0 &&
        data.page === state.listPage && data.page_size === 20 && data.items.length <= data.page_size;
      state.listMeta = paged ? { total: data.total, page: data.page, page_size: data.page_size } : null;
      if (!paged) data = await request(`${API}/runs?limit=200`, {}, ctx);
      state.runs = data.items || [];
      renderListResults();
    } catch (error) { showError($("gg-list-results"), error, ctx); }
  }
  function renderListResults() {
    const query = state.query.trim().toLocaleLowerCase();
    const runs = state.listMeta ? state.runs : state.runs.filter((run) => (!query || `${run.title || ""} ${run.filename || ""}`.toLocaleLowerCase().includes(query)) && (!state.status || run.status === state.status));
    $("gg-list-scope").textContent = state.listMeta
      ? `当前账号共 ${state.listMeta.total} 个匹配任务 · 第 ${state.listPage} 页 · 每页 20 个（服务端搜索与精确状态筛选）`
      : `当前服务未返回可靠分页信息，仅检索最近最多 200 个生成任务（已载入 ${state.runs.length} 个）；当前筛选 ${runs.length} 个，不代表全量任务统计。`;
    $("gg-list-results").innerHTML = runs.length ? `<div class="gg-table-wrap"><table class="gg-table"><thead><tr><th>任务 / 法规</th><th>任务状态</th><th>当前阶段</th><th>候选门禁</th><th>更新时间</th><th>操作</th></tr></thead><tbody>${runs.map((run) => `<tr><td><strong>${esc(run.title || run.filename || "未命名任务")}</strong><small>${esc(run.filename)}</small></td><td>${badge(run.status)}</td><td>${esc(stage(run.stage))}</td><td>${badge(run.qualification_status || "draft")}</td><td>${esc(date(run.updated_at || run.created_at))}</td><td><button class="btn btn-sm" type="button" data-gg-run="${esc(run.id)}" aria-label="查看 ${esc(run.title || run.filename)}">查看</button></td></tr>`).join("")}</tbody></table></div>` : empty(state.listMeta ? "当前页没有匹配任务，请调整筛选或返回上一页。" : state.runs.length ? "当前范围内没有符合筛选条件的任务。" : "还没有生成任务。上传一份法规开始。");
    $("gg-list-pages").innerHTML = state.listMeta ? `<button type="button" class="btn btn-sm" data-gg-list-page="${state.listPage - 1}" ${state.listPage <= 1 ? "disabled" : ""}>上一页</button><span>第 ${state.listPage} / ${Math.max(1, Math.ceil(state.listMeta.total / 20))} 页</span><button type="button" class="btn btn-sm" data-gg-list-page="${state.listPage + 1}" ${state.listPage * 20 >= state.listMeta.total ? "disabled" : ""}>下一页</button>` : "";
  }

  async function renderNew(ctx) {
    const advancedOptions = `<details class="gg-advanced"><summary>高级选项</summary><label class="gg-field" for="gg-corpus-limit">参考合同样本上限（选填）<input id="gg-corpus-limit" type="number" min="1" max="${CORPUS_LIMIT_MAX}" step="1" inputmode="numeric" placeholder="留空使用服务端默认范围" aria-describedby="gg-corpus-limit-hint gg-corpus-limit-error"></label><p id="gg-corpus-limit-hint" class="gg-muted">填写 1—${CORPUS_LIMIT_MAX} 的整数。留空沿用服务端默认范围（可为全库）。设置上限后，输出仅是所选样本范围下的候选指引，不代表全库覆盖；该选项不是费用上限。</p><p id="gg-corpus-limit-error" class="gg-error" role="status" aria-live="polite"></p><label class="gg-check"><input id="gg-latest" type="checkbox" checked> 语义扫描仅参考已知最新合同；历史版本仍参与词法扫描</label><p class="gg-muted">模型、预算上限和语料路径由服务端管理。</p></details>`;
    root().innerHTML =
      `<form id="gg-create" class="gg-create-layout"><section class="card gg-card"><h2>法规文件</h2><p class="gg-muted">支持 DOCX、带文本层 PDF，最大 80 MB。扫描件不支持，不进行 OCR。</p><input id="gg-file" type="file" accept=".docx,.pdf" hidden><div class="gg-upload">${button("pick", "选择法规文件")}<span id="gg-file-label" class="gg-muted">尚未选择文件</span></div><label class="gg-field">任务名称<input id="gg-task-name" readonly value="" placeholder="由法规文件名自动生成"></label>${advancedOptions}<div id="gg-create-status" role="status" aria-live="polite"></div></section><aside class="card gg-card"><h2>生成前确认</h2><h3>参考合同语料（只读）</h3><div id="gg-corpus">${loading()}</div>${note("生成的是候选指引，需人工审阅；发布不会自动启用修改指引。") }<p class="gg-muted">提交后会调用模型并按实际调用计费，受服务端预算限制；上传不保证候选通过核验。</p><label class="gg-check"><input id="gg-cost-ack" type="checkbox" required> 我已确认输入范围及模型调用费用</label><button id="gg-submit" class="btn btn-primary" type="submit" disabled>上传并生成</button></aside></form>`;
    try {
      const data = await request(`${API}/corpus`, {}, ctx);
      $("gg-corpus").innerHTML = `<p>合同版本 ${esc(data.contracts ?? "—")} 份 · 已知最新 ${esc(data.latest_contracts ?? "—")} 份</p><p class="gg-muted">已解析 ${esc(data.parsed ?? "—")} · 解析失败 ${esc(data.parse_failed ?? "—")}</p><p class="gg-muted">当前显示的是可用语料概况；本次任务实际使用范围和快照以任务详情为准。</p>`;
    } catch (error) { if (alive(ctx)) $("gg-corpus").innerHTML = note(`参考语料状态读取失败：${errorMessage(error)}。提交时由服务端检查。`, "warning"); }
  }
  function selectFile(input) {
    const file = input.files?.[0];
    if (!file) return;
    if (!/\.(docx|pdf)$/i.test(file.name) || file.size <= 0 || file.size > 80 * 1024 * 1024) {
      workbench().toast("请选择非空 DOCX 或带文本层 PDF，文件不能超过 80 MB。");
      input.value = "";
      state.file = null;
      $("gg-file-label").textContent = "尚未选择文件";
      $("gg-task-name").value = "";
      updateSubmit();
      return;
    }
    state.file = file;
    $("gg-file-label").textContent = `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MB`;
    $("gg-task-name").value = file.name.replace(/\.[^.]+$/, "");
    updateSubmit();
  }
  function updateSubmit() {
    const validScope = validateCorpusLimit();
    if ($("gg-submit")) $("gg-submit").disabled = !state.file || !$("gg-cost-ack").checked || state.busy || !validScope;
  }
  function validateCorpusLimit() {
    const input = $("gg-corpus-limit");
    if (!input) return true;
    input.setCustomValidity("");
    const raw = input.value;
    const valid = input.validity.valid && (raw === "" || (/^\d+$/.test(raw) && Number.isSafeInteger(Number(raw)) && Number(raw) >= 1 && Number(raw) <= CORPUS_LIMIT_MAX));
    const message = valid ? "" : `请输入 1—${CORPUS_LIMIT_MAX} 的整数，或留空使用服务端默认范围。`;
    input.setCustomValidity(message);
    input.setAttribute("aria-invalid", String(!valid));
    $("gg-corpus-limit-error").textContent = message;
    return valid;
  }
  async function createRun() {
    if (state.busy || !state.file || !$("gg-cost-ack").checked || !validateCorpusLimit()) return;
    const ctx = stamp();
    const form = new FormData();
    form.append("file", state.file);
    const config = { path_b_latest_only: $("gg-latest").checked };
    if ($("gg-corpus-limit").value !== "") config.corpus_limit = Number($("gg-corpus-limit").value);
    form.append("config", JSON.stringify(config));
    state.busy = true;
    updateSubmit();
    $("gg-create-status").textContent = "正在上传法规并创建任务，请勿重复提交…";
    try {
      const run = await request(`${API}/runs`, { method: "POST", body: form }, ctx);
      if (!run?.id) throw new Error("服务未返回有效任务编号，请刷新列表核对，避免重复提交。");
      state.file = null;
      state.busy = false;
      workbench().toast("任务已创建，可在详情页查看真实处理阶段。");
      navigate({ mode: "detail", id: run.id, tab: "overview" });
    } catch (error) { if (alive(ctx)) $("gg-create-status").textContent = errorMessage(error); }
    finally { if (alive(ctx)) { state.busy = false; updateSubmit(); } }
  }

  async function loadDetail(ctx) {
    root().innerHTML = `<h1 class="object-title">正在读取任务…</h1>` + loading();
    try {
      state.detail = await request(runPath(), {}, ctx);
      root().innerHTML = `<div id="gg-detail-head"></div><nav class="gg-tabs" aria-label="生成任务详情">${Object.entries(TABS).map(([key, title]) => `<button type="button" data-gg-tab="${key}" class="gg-tab ${key === state.route.tab ? "is-active" : ""}" aria-current="${key === state.route.tab ? "page" : "false"}">${title}</button>`).join("")}</nav><div id="gg-panel" aria-live="polite">${loading()}</div>`;
      renderDetailHead();
      await loadTab(ctx);
      schedulePoll(ctx);
    } catch (error) {
      if (!alive(ctx)) return;
      root().innerHTML = '<h1 class="object-title">任务暂不可用</h1><div id="gg-detail-error"></div>';
      showError($("gg-detail-error"), error, ctx);
    }
  }
  function renderDetailHead() {
    const run = state.detail;
    if (!$("gg-detail-head")) return;
    workbench().setObjectTitle?.("generation", run.title || run.filename);
    const source = run.filename && run.filename !== run.title ? `${run.filename} · ` : "";
    $("gg-detail-head").innerHTML = heading(run.title || run.filename || "未命名任务", `${source}更新 ${date(run.updated_at || run.created_at)}`, button("refresh", "刷新")) +
      `<div class="gg-task-status"><span class="gg-status-field"><strong>任务</strong>${badge(run.status)}</span><span class="gg-status-field"><strong>候选门禁</strong>${badge(run.qualification_status || "draft")}</span>${run.candidate && run.candidate.status !== run.qualification_status ? `<span class="gg-status-field"><strong>当前版本</strong>${badge(run.candidate.status)}</span>` : ""}<span class="gg-status-field"><strong>阶段</strong>${esc(stage(run.stage))}</span></div>${Number.isInteger(run.config?.corpus_limit) ? `<div id="gg-run-scope">${note(`本任务参考合同样本上限：${run.config.corpus_limit} 份。输出仅是所选样本范围下的候选指引，不代表全库覆盖；实际使用范围以任务快照为准。`, "warning")}</div>` : ""}${runProblem(run.error_code)}${run.retry ? `<div class="gg-retry"><span>处理尝试 ${esc(run.retry.attempts ?? "—")} / ${esc(run.retry.max_attempts ?? "—")} 次</span>${run.retry.can_resume === true && ["failed", "paused"].includes(run.status) ? `${button("resume", "继续处理/重试")}<p class="gg-muted">继续处理将再次调用模型、消耗预算并可能产生费用；仍受服务端预算及尝试次数上限约束。不会自动执行付费重试。</p>` : ""}<span id="gg-resume-status" role="status" aria-live="polite"></span></div>` : ""}`;
  }
  async function resumeRun(trigger) {
    if (state.busy || state.detail?.retry?.can_resume !== true || !["failed", "paused"].includes(state.detail.status)) return;
    if (!window.confirm(`确认继续处理此任务？当前处理尝试 ${state.detail.retry.attempts} / ${state.detail.retry.max_attempts} 次。继续将调用真实模型、消耗预算并可能产生费用；不会增加服务端预算或尝试次数上限。`)) return;
    const ctx = stamp();
    state.busy = true;
    trigger.disabled = true;
    $("gg-resume-status").textContent = "正在请求继续处理，请勿重复操作…";
    try {
      await request(runPath("/resume"), { method: "POST" }, ctx);
      state.busy = false;
      workbench().toast("继续处理已排队；实际阶段和尝试次数以后台记录为准。");
      await open(state.route);
    } catch (error) {
      if (alive(ctx)) $("gg-resume-status").textContent = errorMessage(error);
    } finally {
      if (alive(ctx)) { state.busy = false; trigger.disabled = false; }
    }
  }
  async function loadTab(ctx) {
    const target = $("gg-panel");
    try {
      if (state.route.tab === "overview") target.innerHTML = overview();
      if (state.route.tab === "guide") {
        const [guide, requirements] = await Promise.all([
          request(runPath("/guide"), {}, ctx), request(runPath("/requirements"), {}, ctx),
        ]);
        state.guide = guide;
        state.requirements = requirements.items || [];
        if (!(guide.items || []).some((item) => item.guide_item_id === state.selected)) state.selected = guide.items?.[0]?.guide_item_id || "";
        renderGuide();
      }
      if (state.route.tab === "requirements") {
        const data = await request(runPath("/requirements"), {}, ctx);
        state.requirements = data.items || [];
        renderRequirements();
        await loadImpacts(ctx);
      }
      if (state.route.tab === "issues") await loadIssues(ctx);
      if (state.route.tab === "versions") {
        state.candidate = await request(runPath("/candidate"), {}, ctx);
        renderVersions();
      }
    } catch (error) { showError(target, error, ctx); }
  }
  function overview() {
    const run = state.detail;
    const summary = run.summary || {};
    const finalize = summary.finalize || {};
    const stats = run.stats || {};
    const steps = new Map((run.stages || []).map((step) => [step.stage, step]));
    return `<div class="gg-metrics">${metric("法规要求", stats.requirements, "来自上传法规")}${metric("合同影响", stats.impacts, "包括可能影响")}${metric("候选条目", stats.guide_items, "尚需人工审阅")}${metric("关键质量问题", finalize.critical_quality_findings, "非全部质量问题")}</div>` +
      card("处理进度", `<p class="gg-muted">只展示实际阶段记录，不估算完成百分比。生成结束后仍需完成候选核验。</p><ol class="gg-stages">${Object.entries(STAGES).map(([key, title]) => { const step = steps.get(key); return `<li class="${step?.status === "running" ? "is-current" : ""}"><span>${esc(title)}</span>${step ? badge(step.status) : '<span class="gg-muted">尚无记录</span>'}${step?.error_code ? `<small class="gg-error">${esc(step.error_code)}</small>` : ""}</li>`; }).join("")}</ol>`) +
      card("候选审阅门禁", gateChecklist(finalize) + `<div class="gg-actions">${button("issues", "查看待处理问题")}${button("versions", "查看版本与导出")}</div>`) +
      card("来源与使用边界", `<dl class="gg-meta"><dt>任务编号</dt><dd><code>${esc(run.id)}</code></dd><dt>参考合同快照</dt><dd><code>${esc(run.corpus_snapshot_id || "尚未建立")}</code></dd><dt>候选版本</dt><dd><code>${esc(run.candidate?.current_version_id || "尚未生成")}</code></dd></dl>`);
  }
  function gateChecklist(finalize) {
    const checks = finalize.checklist || {};
     return Object.keys(checks).length ? `<ul class="gg-checklist">${Object.entries(checks).map(([key, value]) => `<li><span class="${value === true ? "gg-success" : "gg-warning"}">${value === true ? "✓ 通过" : "! 未通过"}</span> ${esc(CHECKS[key] || key)}</li>`).join("")}</ul><p class="gg-muted">这些结论来自生成时的核验；人工版本保存后需重新审阅。</p>` : empty("尚无完整核验结论；不能据此判断候选已通过。");
  }
  function boundary() {
    return note("候选发布 ≠ 修改指引启用。尚未通过此工作区导入修改引擎（runtime_guide_import=not_requested）；当前启用状态未由此接口确认。需要导出后在“修改指引”中显式导入、核验并启用。不会自动改变当前修改任务的指引。", "warning");
  }
  function schedulePoll(ctx) {
    clearTimeout(state.timer);
    if (!alive(ctx) || !["queued", "running"].includes(state.detail?.status)) return;
    state.timer = setTimeout(async () => {
      try {
        const detail = await request(runPath(), {}, ctx);
        if (dirty()) { schedulePoll(ctx); return; }
        state.detail = detail;
        renderDetailHead();
        if (state.route.tab === "overview") $("gg-panel").innerHTML = overview();
        // Other tabs are not replaced underneath the reader or editor.
        schedulePoll(ctx);
      } catch (error) { notify(error, ctx); }
    }, 5000);
  }

  function editable() { return complete() && state.detail?.candidate?.status !== "published" && Boolean(state.detail?.candidate?.current_version_id); }
  function itemValues(item) {
    return Object.fromEntries(Object.keys(FIELDS).map((field) => [field, LIST_FIELDS.has(field) ? (item[field] || []) : (item[field] || "")]));
  }
  function renderGuide() {
    const items = state.guide.items || [];
    $("gg-panel").innerHTML = `<div class="gg-guide-bar"><div><strong>${items.length} 条候选指引</strong><p class="gg-muted">逐条审阅适用范围、新文及法规证据。保存会创建可追溯的人工版本，不自动进行付费模型复核。</p></div><div class="gg-actions"><span id="gg-dirty-count" role="status">${state.drafts.size ? `${state.drafts.size} 条未保存` : "无未保存编辑"}</span>${button("discard", "放弃未保存编辑")}</div></div>${!editable() ? note(state.detail.candidate?.status === "published" ? "该候选已发布，内容只读，不能静默改写已发布版本。" : "任务尚未结束或候选版本尚不可用；当前仅供查看。") : note("人工修订会使该条目的质量状态变为待审阅；既有质量、覆盖和补漏结论不等于新版本已复核。")}${items.length ? `<div class="gg-guide-layout"><nav class="card gg-card gg-directory" aria-label="候选条目目录">${items.map((item, index) => `<button type="button" class="gg-item-link ${item.guide_item_id === state.selected ? "is-active" : ""}" data-gg-item="${esc(item.guide_item_id)}" aria-current="${item.guide_item_id === state.selected ? "true" : "false"}"><small>${index + 1} · ${esc(item.section || "未分组")}</small><strong>${esc(item.title || item.guide_item_id)}</strong><span data-gg-dirty-item="${esc(item.guide_item_id)}">${state.drafts.has(item.guide_item_id) ? "未保存" : ""}</span></button>`).join("")}</nav><section class="card gg-card" id="gg-editor"></section><aside class="card gg-card" id="gg-guide-evidence"></aside></div>` : empty("尚无候选指引。可返回总览查看处理进度或异常。")}`;
    if (items.length) renderEditor();
  }
  function renderEditor() {
    const item = state.guide.items.find((entry) => entry.guide_item_id === state.selected);
    if (!item) return;
    const values = state.drafts.get(state.selected) || itemValues(item);
    const disabled = !editable() || state.busy;
    $("gg-editor").innerHTML = `<h2>${esc(item.title || item.guide_item_id)}</h2><p><code>${esc(item.guide_item_id)}</code> ${badge(item.quality_status)} ${badge(item.coverage_status)}</p><div class="gg-editor-fields">${Object.entries(FIELDS).map(([field, title]) => `<label class="gg-field">${title}${field === "new_text_origin" ? `<select data-gg-field="${field}" ${disabled ? "disabled" : ""}>${["model_drafted", "regulation_verbatim", "contract_pattern_adapted"].map((origin) => `<option value="${origin}" ${values[field] === origin ? "selected" : ""}>${esc(label(origin))}</option>`).join("")}</select>` : field === "title" ? `<input data-gg-field="${field}" value="${esc(values[field])}" ${disabled ? "disabled" : ""}>` : `<textarea data-gg-field="${field}" rows="${field === "new_text" ? 7 : 3}" ${disabled ? "disabled" : ""}>${esc(text(values[field]))}</textarea>`}</label>`).join("")}</div><div class="gg-actions"><button type="button" class="btn btn-primary" data-gg-action="save" ${disabled || !state.drafts.has(item.guide_item_id) ? "disabled" : ""}>保存本条人工修订</button><span id="gg-save-status" role="status" aria-live="polite"></span></div>`;
    const reqs = state.requirements.filter((req) => (item.requirement_ids || []).includes(req.requirement_id));
    $("gg-guide-evidence").innerHTML = `<h2>本条证据</h2><h3>法规要求</h3>${reqs.map((req) => `<div class="gg-evidence-entry"><strong>${esc(req.article || req.requirement_id)}</strong><p>${esc(req.requirement)}</p>${quote(req.source_quote)}<small>${esc(req.requirement_id)}</small></div>`).join("") || empty("尚无法读取关联法规原文，请到“法规依据”核对。") }<h3>合同影响</h3><p class="gg-muted">关联 ${(item.impact_ids || []).length} 条影响；完整合同原文和处理理由请查看法规依据。</p><p class="gg-muted">${esc((item.impact_ids || []).join("、"))}</p>${button("requirements", "查看法规与合同证据")}<h3>建议新文来源</h3><p>${esc(label(values.new_text_origin))}</p>`;
  }
  function recordDraft() {
    const item = state.guide?.items?.find((entry) => entry.guide_item_id === state.selected);
    if (!item || !editable() || state.busy) return;
    const values = {};
    $("gg-editor").querySelectorAll("[data-gg-field]").forEach((field) => {
      const name = field.dataset.ggField;
      values[name] = LIST_FIELDS.has(name) ? field.value.split("\n").map((value) => value.trim()).filter(Boolean) : field.value;
    });
    if (JSON.stringify(values) === JSON.stringify(itemValues(item))) state.drafts.delete(state.selected);
    else state.drafts.set(state.selected, values);
    $("gg-dirty-count").textContent = state.drafts.size ? `${state.drafts.size} 条未保存` : "无未保存编辑";
    root().querySelectorAll("[data-gg-dirty-item]").forEach((entry) => { entry.textContent = state.drafts.has(entry.dataset.ggDirtyItem) ? "未保存" : ""; });
    root().querySelector('[data-gg-action="save"]').disabled = !state.drafts.has(state.selected);
  }
  async function saveItem() {
    if (state.busy || !editable() || !state.drafts.has(state.selected)) return;
    const ctx = stamp();
    const itemId = state.selected;
    const versionId = state.detail.candidate.current_version_id;
    const payload = { ...state.drafts.get(itemId), expected_current_version_id: versionId };
    state.busy = true;
    renderEditor();
    $("gg-save-status").textContent = "保存中…";
    try {
      const result = await request(runPath(`/guide/items/${encodeURIComponent(itemId)}`), { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }, ctx);
      if (!result.item) throw new Error("保存响应不完整，请保留编辑内容并刷新核对。");
      state.guide.items = state.guide.items.map((item) => item.guide_item_id === itemId ? result.item : item);
      state.drafts.delete(itemId);
      if (result.candidate_version) {
        const version = result.candidate_version;
        state.detail.candidate = { ...state.detail.candidate, status: version.status, current_version_id: version.candidate_version_id, current_version_no: version.version_no };
      }
      if (result.guide_sha256) state.guide.guide_sha256 = result.guide_sha256;
      state.busy = false;
      renderDetailHead();
      renderGuide();
      $("gg-save-status").textContent = result.version_no ? "已保存为人工版本；尚未自动重新核验。" : "内容未变化，无需创建新版本。";
    } catch (error) {
      if (alive(ctx)) {
        state.busy = false;
        renderEditor();
        $("gg-save-status").textContent = errorMessage(error);
      }
    } finally { if (alive(ctx)) state.busy = false; }
  }

  function renderRequirements() {
    $("gg-panel").innerHTML = card("法规要求与原文", `<p class="gg-muted">共 ${state.requirements.length} 条法规要求；每条要求的适用条件、例外与处理去向均需结合原文审阅。</p>${state.requirements.map((req) => `<details class="gg-requirement"><summary><strong>${esc(req.article || req.requirement_id)}</strong> ${badge(req.disposition || "pending")}<span>${esc(req.requirement)}</span></summary><div class="gg-evidence-entry"><p>${esc(req.requirement)}</p>${quote(req.source_quote, "法规原文")}<dl class="gg-meta"><dt>要求编号</dt><dd>${esc(req.requirement_id)}</dd><dt>处理理由</dt><dd>${esc(req.disposition_reason || "尚未说明")}</dd><dt>条件</dt><dd>${esc((req.conditions || []).join("；") || "未列出")}</dd><dt>例外</dt><dd>${esc((req.exceptions || []).join("；") || "未列出")}</dd></dl><button class="btn btn-sm" type="button" data-gg-req="${esc(req.requirement_id)}">查看本要求的合同影响</button></div></details>`).join("") || empty("尚无已提取的法规要求。")}`) +
      card("合同影响与证据", `<form id="gg-impact-filter" class="gg-toolbar"><label>关联要求<select id="gg-impact-req"><option value="">全部要求</option>${state.requirements.map((req) => `<option value="${esc(req.requirement_id)}" ${req.requirement_id === state.impactRequirement ? "selected" : ""}>${esc(req.requirement_id)} · ${esc(req.article || "法规要求")}</option>`).join("")}</select></label><label>影响状态<select id="gg-impact-status"><option value="">全部影响</option>${["definite", "possible", "unlikely"].map((value) => `<option value="${value}" ${value === state.impactStatus ? "selected" : ""}>${label(value)}</option>`).join("")}</select></label><button type="submit" class="btn">筛选</button></form><div id="gg-impacts">${loading()}</div>`);
  }
  async function loadImpacts(ctx) {
    const seq = ++state.impactsSerial;
    const params = new URLSearchParams({ page: String(state.impactPage), page_size: "50", requirement_id: state.impactRequirement, status: state.impactStatus });
    const target = $("gg-impacts");
    target.innerHTML = loading();
    try {
      const data = await request(runPath(`/impacts?${params}`), {}, ctx);
      if (seq !== state.impactsSerial) return;
      target.innerHTML = `<p class="gg-muted">筛选结果 ${esc(data.total ?? "—")} 条 · 第 ${state.impactPage} 页</p>${(data.items || []).map((impact) => `<details class="gg-requirement"><summary>${badge(impact.impact_status)}<strong>${esc(impact.impact_id)}</strong><span>${esc(impact.impact_reason || "查看合同原文与处理去向")}</span></summary><div class="gg-evidence-entry"><p class="gg-muted">合同版本：${esc(impact.contract_version_id)} · 法规要求：${esc(impact.requirement_id)}</p>${quote(impact.source_text, "合同原文")}<p><strong>影响理由：</strong>${esc(impact.impact_reason || "未说明")}</p><p><strong>处理去向：</strong>${esc(label(impact.disposition || "pending"))}</p><p>${esc(impact.disposition_reason)}</p><p class="gg-muted">关联候选条目：${esc((impact.guide_item_ids || []).join("、") || "尚无")}</p></div></details>`).join("") || empty("当前筛选下尚无合同影响记录。") }<div class="gg-pagination"><button class="btn btn-sm" type="button" data-gg-page="${state.impactPage - 1}" ${state.impactPage <= 1 ? "disabled" : ""}>上一页</button><span>第 ${state.impactPage} 页</span><button class="btn btn-sm" type="button" data-gg-page="${state.impactPage + 1}" ${state.impactPage * 50 >= (data.total || 0) ? "disabled" : ""}>下一页</button></div>`;
    } catch (error) { if (seq === state.impactsSerial) showError(target, error, ctx); }
  }

  async function loadIssues(ctx) {
    // Independent endpoint failures must not erase the other review evidence.
    const results = await Promise.allSettled(["/quality", "/coverage?limit=5000", "/residual"].map((suffix) => request(runPath(suffix), {}, ctx)));
    if (!alive(ctx)) return;
    const [quality, coverage, residual] = results.map((result) => result.status === "fulfilled" ? result.value : null);
    const finalize = state.detail.summary?.finalize || {};
    const findings = quality?.findings || [];
    const openFindings = findings.filter((entry) => !["resolved", "closed", "dismissed"].includes(entry.status));
    const rows = (coverage?.items || []).filter((row) => ["gap", "uncertain", "unresolved"].includes(row.status));
    const counts = `<div class="gg-metrics">${metric("待处理质量记录", quality ? openFindings.length : null, "不含已解决 / 已关闭记录")}${metric("法规要求缺口", finalize.requirement_gaps, "生成时完整统计")}${metric("未解决合同影响", finalize.unresolved_impacts, "生成时完整统计")}${metric("最新合同不确定项", finalize.latest_contract_uncertain, "生成时完整统计")}</div>`;
    const failed = results.map((result, index) => result.status === "rejected" ? note(`${["质量核验", "覆盖核验", "补漏核验"][index]}读取失败：${errorMessage(result.reason)}`, "error") : "").join("");
    $("gg-panel").innerHTML = failed + counts +
      card("质量核验", `${badge(quality?.summary?.run_status || "not_run")}<p class="gg-muted">质量记录共 ${quality ? findings.length : "—"} 条；待处理 ${quality ? openFindings.length : "—"} 条，其中关键 ${quality ? openFindings.filter((entry) => entry.severity === "critical").length : "—"} 条。关键发布门禁以总览清单为准。</p>${findings.map((finding) => `<details class="gg-requirement"><summary>${badge(finding.severity)} ${badge(finding.status || "open")}<span>${esc(finding.description || finding.category)}</span></summary><div class="gg-evidence-entry"><p>${esc(finding.description)}</p><p><strong>建议：</strong>${esc(finding.recommendation || "请人工核对证据与候选条目。")}</p><p class="gg-muted">条目：${esc(finding.guide_item_id || "未关联")} · 类别：${esc(finding.category)}</p>${quote(finding.evidence_quote)}</div></details>`).join("") || empty(quality ? "暂无质量问题记录；不代表未运行的质量核验已通过。" : "质量数据不可用。")}`) +
      card("覆盖缺口与不确定项", `<p class="gg-muted">覆盖接口共 ${esc(coverage?.total ?? "—")} 条记录，本次读取 ${(coverage?.items || []).length} 条（上限 5000），其中缺口 / 不确定 / 未解决记录 ${coverage ? rows.length : "—"} 条；不同层级不合并为任务总数。${coverage && coverage.total > coverage.items.length ? "存在未展示记录，请下载完整证据核查。" : ""}</p>${rows.map((row) => `<div class="gg-issue-row">${badge(row.status)}<strong>${esc(label(row.level))} · ${esc(row.ref_id)}</strong><p>${esc(row.reason || "尚无说明，请结合完整证据核对。")}</p></div>`).join("") || empty(coverage ? "已读取记录中暂无缺口；仍需核对完整统计及核验是否完成。" : "覆盖数据不可用。")}`) +
      card("条目适用性核验", applicabilityIssues(coverage)) +
      card("查漏补缺", `<p>${residual?.summary?.saturated === true ? badge("saturated") : badge(residual?.summary?.status || "not_run")}</p>${note("补漏停止仅表示在当前检索、扫描、复核和补漏策略下未发现新缺口，不是对完整性的 100% 证明。")}${(residual?.rounds || []).map(residualRound).join("") || empty(residual ? "尚无补漏轮次记录，不能判断已达到停止条件。" : "补漏数据不可用。")}`) +
      card("发布门禁", gateChecklist(finalize) + `<div class="gg-actions">${button("guide", "审阅候选指引")}${button("versions", "版本与导出")}</div>`);
  }
  function applicabilityIssues(coverage) {
    if (!coverage) return empty("适用性数据不可用。");
    const samples = coverage.applicability || [];
    const issues = samples.filter((row) => ["ambiguous", "not_covered", "uncertain", "unresolved"].includes(row.verdict));
    return `<p class="gg-muted">读取 ${samples.length} 条适用性核验记录，其中 ${issues.length} 条需关注（最多读取 5000 条，不能推断全量已通过）。</p>${issues.map((row) => `<div class="gg-issue-row">${badge(row.verdict)}<strong>${esc(row.guide_item_id)} · ${esc(row.clause_id)}</strong><p>${esc(row.reason)}</p>${quote(row.evidence_quote, "适用性证据")}</div>`).join("") || empty("已读取样本中暂无适用性问题记录；无记录不等于已经核验通过。")}`;
  }
  function residualRound(round) {
    const uncovered = round.uncovered || [];
    return `<details class="gg-requirement"><summary><strong>第 ${esc(round.round_no)} 轮</strong> ${badge(round.status)}<span>新模式 ${esc(round.new_patterns ?? "—")} · 新合同影响 ${esc(round.new_impacts ?? "—")} · 发现记录 ${uncovered.length} 条</span></summary><div class="gg-evidence-entry">${round.error_code ? note(round.error_code, "error") : ""}${uncovered.map((entry) => `<div class="gg-issue-row"><strong>${esc(entry.pattern_description || entry.pattern_key || "补漏发现")}</strong><p>${esc(entry.reason)}</p><p class="gg-muted">合同版本：${esc(entry.contract_version_id)} · 要求：${esc((entry.requirement_ids || []).join("、"))}</p>${quote(entry.evidence_quote, "补漏原文证据")}</div>`).join("") || empty("本轮未列出新的发现记录；仍需结合轮次状态及总览门禁判断。")}</div></details>`;
  }

  function renderVersions() {
    const candidate = state.candidate;
    const versions = candidate.versions || [];
    const current = versions.find((version) => version.candidate_version_id === candidate.current_version_id);
    const qualification = state.detail.qualification_status;
    const canApprove = complete() && Boolean(current) && (current.status === "human_draft" || (current.status === "candidate_ready" && qualification === "candidate_ready"));
    const canPublish = complete() && current?.status === "approved";
     $("gg-panel").innerHTML = card("当前候选与发布", `<p>当前版本 v${esc(current?.version_no ?? "—")} · ${badge(candidate.status)}</p><p class="gg-muted">审批和发布仅针对下列精确版本，若版本发生变化服务端将拒绝操作。发布后内容只读。</p><code class="gg-version-id">${esc(candidate.current_version_id)}</code>${qualification === "candidate_with_findings" ? note("生成资格仍为“存在待处理问题”，不作为 AI 候选可批准的依据。人工草稿也必须由审阅者结合原问题重新确认。", "warning") : ""}${current?.status === "human_draft" ? note("人工修订未自动重跑模型核验。批准表示你已审阅当前人工版本及尚存问题，不表示系统重新验证通过。", "warning") : ""}<div class="gg-actions"><button type="button" class="btn" data-gg-transition="approve" ${canApprove ? "" : "disabled"}>批准当前精确版本</button><button type="button" class="btn btn-primary" data-gg-transition="publish" ${canPublish ? "" : "disabled"}>发布已批准版本</button></div>${boundary()}`) +
       card("不可变版本链", `${versions.length ? `<ol class="gg-version-chain">${versions.map((version) => `<li><div class="gg-actions"><strong>版本 ${esc(version.version_no)}</strong>${badge(version.status)}${version.candidate_version_id === candidate.current_version_id ? '<span class="gg-muted">当前版本</span>' : ""}</div><dl class="gg-meta"><dt>版本编号</dt><dd><code>${esc(version.candidate_version_id)}</code></dd><dt>父版本</dt><dd><code>${esc(version.parent_version_id || "初始版本")}</code></dd><dt>创建时间</dt><dd>${esc(date(version.created_at))}</dd>${version.approved_at ? `<dt>批准</dt><dd>${esc(version.approved_by)} · ${esc(date(version.approved_at))}</dd>` : ""}${version.published_at ? `<dt>发布</dt><dd>${esc(version.published_by)} · ${esc(date(version.published_at))}</dd>` : ""}</dl></li>`).join("")}</ol>` : empty("尚无可审阅候选版本。")}`) +
      card("版本内容对照", versions.length > 1 ? `<div class="gg-toolbar"><label>原版本<select id="gg-version-from">${versions.map((version, index) => `<option value="${index}" ${index === versions.length - 2 ? "selected" : ""}>版本 ${esc(version.version_no)}</option>`).join("")}</select></label><label>新版本<select id="gg-version-to">${versions.map((version, index) => `<option value="${index}" ${index === versions.length - 1 ? "selected" : ""}>版本 ${esc(version.version_no)}</option>`).join("")}</select></label>${button("compare-versions", "比较内容")}</div><div id="gg-version-diff"></div>` : empty("至少有两个版本后可进行内容对照。")) +
       card("授权导出", `<p class="gg-muted">下载文件仅供当前候选审阅；正式使用前请完成批准、发布和修改指引启用。历史版本仅在服务端实际提供时显示。</p><div class="gg-actions">${Object.entries(DOWNLOADS).filter(([kind]) => Boolean(state.detail.artifacts?.[kind])).map(([kind, [title]]) => `<button type="button" class="btn" data-gg-download="${kind}">${title}</button>`).join("") || empty("尚无可下载产物。")}</div><p class="gg-muted">引擎兼容状态：${esc(label(state.detail.engine_status || "not_run"))}；兼容报告不等于质量与覆盖已通过。</p>`);
    if (versions.length > 1) compareVersions();
  }
  function compareVersions() {
    const versions = state.candidate.versions;
    const before = versions[Number($("gg-version-from").value)]?.payload?.guide_items;
    const after = versions[Number($("gg-version-to").value)]?.payload?.guide_items;
    const target = $("gg-version-diff");
    if (!Array.isArray(before) || !Array.isArray(after)) { target.innerHTML = empty("所选版本没有条目快照，无法进行内容对照。请查看完整证据。"); return; }
    const oldItems = new Map(before.map((item) => [item.guide_item_id, item]));
    const newItems = new Map(after.map((item) => [item.guide_item_id, item]));
    const changes = [];
    for (const id of new Set([...oldItems.keys(), ...newItems.keys()])) {
      const oldItem = oldItems.get(id);
      const newItem = newItems.get(id);
      for (const [field, title] of Object.entries(FIELDS)) {
        const left = text(oldItem?.[field]);
        const right = text(newItem?.[field]);
        if (left !== right) changes.push(`<div class="gg-diff"><strong>${esc(id)} · ${esc(title)}</strong><div class="gg-diff-columns"><div><small>原版本${oldItem ? "" : "（无此条目）"}</small><pre>${esc(left || "（空）")}</pre></div><div><small>新版本${newItem ? "" : "（无此条目）"}</small><pre>${esc(right || "（空）")}</pre></div></div></div>`);
      }
    }
    target.innerHTML = changes.join("") || empty("所选版本的可编辑字段无内容差异。");
  }
  async function transition(action, trigger) {
    if (state.busy || !state.candidate?.current_version_id) return;
    const current = state.candidate.versions.find((version) => version.candidate_version_id === state.candidate.current_version_id);
    const canApprove = current?.status === "human_draft" || (current?.status === "candidate_ready" && state.detail.qualification_status === "candidate_ready");
    if (!complete() || (action === "approve" ? !canApprove : current?.status !== "approved")) return;
    const id = state.candidate.current_version_id;
    if (!window.confirm(`${action === "approve" ? "确认已审阅并批准" : "确认发布已批准的"}候选版本 ${current.version_no}（${id}）？${action === "publish" ? "发布后只读；不会导入或启用修改引擎。" : "人工修改不会自动重新运行模型核验。"}`)) return;
    const ctx = stamp();
    state.busy = true;
    trigger.disabled = true;
    try {
      await request(runPath(`/candidate/${action}`), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ version_id: id }) }, ctx);
      state.busy = false;
      workbench().toast(action === "publish" ? "候选已发布，尚未导入或启用修改引擎。" : "该精确版本已批准。尚未发布。" );
      await open(state.route);
    } catch (error) { notify(error, ctx); }
    finally { if (alive(ctx)) { state.busy = false; trigger.disabled = false; } }
  }
  async function download(kind, trigger) {
    if (!DOWNLOADS[kind] || !state.detail.artifacts?.[kind]) return;
    const ctx = stamp();
    trigger.disabled = true;
    try {
      if (typeof workbench().download !== "function") throw new Error("工作台授权下载暂不可用，请刷新页面后重试。");
      // Never navigate to a raw URL or persist credentials in links/storage.
      await workbench().download(runPath(`/download/${encodeURIComponent(kind)}`), DOWNLOADS[kind][1]);
    } catch (error) { notify(error, ctx); }
    finally { if (alive(ctx)) trigger.disabled = false; }
  }

  function reset() {
    clearTimeout(state.timer);
    state.serial++;
    state.active = false;
    state.route = null;
    state.detail = null;
    state.guide = null;
    state.candidate = null;
    state.requirements = [];
    state.drafts.clear();
    state.file = null;
    state.runs = [];
    state.query = "";
    state.status = "";
    state.listPage = 1;
    state.listMeta = null;
    state.selected = "";
    state.busy = false;
    state.impactPage = 1;
    state.impactRequirement = "";
    state.impactStatus = "";
    state.impactsSerial++;
    state.openEpoch = null;
    if (root()) root().replaceChildren();
  }
  document.addEventListener("fundlex:route", (event) => {
    if (event.detail?.view === "generation") {
      const route = event.detail;
      if (workbench()?.ready && !workbench().ready()) return;
      // Capability refreshes re-emit the current route; never erase live drafts.
      if (state.active && state.openEpoch === workbench().epoch() && state.authValue === workbench().authenticated() &&
          state.route?.mode === (route.mode || "list") && state.route?.id === (route.id || "") &&
          state.route?.tab === (TABS[route.tab] ? route.tab : "overview") &&
          state.route?.page === String(route.page == null ? state.listPage : routePage(route.page)) &&
          state.route?.q === String(route.q ?? state.query) && state.route?.status === String(route.status ?? state.status) && root()?.hasChildNodes()) return;
      void open(route);
    }
    else {
      clearTimeout(state.timer);
      state.active = false;
      state.serial++;
      state.drafts.clear();
      state.file = null;
      state.busy = false;
    }
  });
  document.addEventListener("fundlex:identity-reset", reset);
  window.addEventListener("beforeunload", (event) => { if (state.active && dirty()) { event.preventDefault(); event.returnValue = ""; } });
  document.addEventListener("submit", (event) => {
    if (!state.active || !root()?.contains(event.target)) return;
    if (event.target.id === "gg-create") { event.preventDefault(); void createRun(); }
    if (event.target.id === "gg-filter") {
      event.preventDefault();
      navigate({ mode: "list", page: "1", q: $("gg-query").value.trim(), status: $("gg-status").value });
    }
    if (event.target.id === "gg-impact-filter") {
      event.preventDefault();
      state.impactRequirement = $("gg-impact-req").value;
      state.impactStatus = $("gg-impact-status").value;
      state.impactPage = 1;
      void loadImpacts(stamp());
    }
  });
  document.addEventListener("change", (event) => {
    if (!state.active || !root()?.contains(event.target)) return;
    if (event.target.id === "gg-file") selectFile(event.target);
    if (event.target.id === "gg-cost-ack") updateSubmit();
    if (event.target.id === "gg-corpus-limit") updateSubmit();
    if (event.target.matches("[data-gg-field]")) recordDraft();
  });
  document.addEventListener("input", (event) => {
    if (!state.active || !root()?.contains(event.target)) return;
    if (event.target.matches("[data-gg-field]")) recordDraft();
    if (event.target.id === "gg-corpus-limit") updateSubmit();
  });
  document.addEventListener("click", (event) => {
    const target = event.target.closest("button");
    if (!state.active || !target || !root()?.contains(target) || target.disabled) return;
    if (target.dataset.ggRun) { state.impactPage = 1; state.impactRequirement = ""; state.impactStatus = ""; navigate({ mode: "detail", id: target.dataset.ggRun, tab: "overview" }); }
    if (target.dataset.ggTab) navigate({ mode: "detail", id: state.route.id, tab: target.dataset.ggTab });
    if (target.dataset.ggItem && !state.busy) { state.selected = target.dataset.ggItem; renderGuide(); }
    if (target.dataset.ggReq) {
      state.impactRequirement = target.dataset.ggReq;
      state.impactPage = 1;
      $("gg-impact-req").value = state.impactRequirement;
      void loadImpacts(stamp());
      $("gg-impacts").scrollIntoView({ block: "nearest" });
    }
    if (target.dataset.ggPage) { state.impactPage = Number(target.dataset.ggPage); void loadImpacts(stamp()); }
    if (target.dataset.ggListPage) navigate({ mode: "list", page: target.dataset.ggListPage });
    if (target.dataset.ggTransition) void transition(target.dataset.ggTransition, target);
    if (target.dataset.ggDownload) void download(target.dataset.ggDownload, target);
    const action = target.dataset.ggAction;
    if (action === "new" || action === "list") navigate({ mode: action });
    if (TABS[action]) navigate({ mode: "detail", id: state.route.id, tab: action });
    if (action === "pick" && !state.busy) $("gg-file").click();
    if (action === "refresh") {
      if (state.busy || (dirty() && !window.confirm("刷新会放弃尚未保存的编辑或已选文件，是否继续？"))) return;
      void open(state.route);
    }
    if (action === "save") void saveItem();
    if (action === "resume") void resumeRun(target);
    if (action === "discard" && !state.busy && state.drafts.size && window.confirm("确定放弃所有未保存编辑，并读取服务端最新版本？")) void open(state.route);
    if (action === "compare-versions") compareVersions();
  });
  window.FundLexGuideGeneration = { open, hasUnsavedChanges: () => state.active && dirty() };
  // app.js may have emitted its first deep link before this deferred script ran.
  const initial = workbench()?.route?.();
  if (initial?.view === "generation" && (!workbench().ready || workbench().ready())) void open(initial);
})();
