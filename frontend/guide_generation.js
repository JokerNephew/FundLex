(() => {
  "use strict";
  const BASE = (document.querySelector('meta[name="fundlex-base-path"]')?.content || "").replace(/\/$/, "");
  const TOKEN_KEY = "fundlex-auth-token";
  const USER_KEY = "fundlex-auth-user";
  const DEV_KEY = "fundlex-dev-user";
  const state = {
    runs: [], current: null, detail: null, tab: "overview",
    requirements: null, impacts: null, impactPage: 1, impactTotal: 0, impactReq: "", impactStatus: "",
    guide: null, quality: null, coverage: null, residual: null,
    coverageLevel: "", coverageStatus: "", pollTimer: null, saving: false,
  };

  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
  const token = () => { try { return sessionStorage.getItem(TOKEN_KEY) || ""; } catch { return ""; } };
  const devUser = () => { try { return localStorage.getItem(DEV_KEY) || "local-user"; } catch { return "local-user"; } };

  function toast(message) {
    const box = $("gg-toast");
    box.textContent = message;
    box.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { box.hidden = true; }, 4200);
  }

  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    const auth = token();
    if (auth) headers.set("Authorization", `Bearer ${auth}`);
    if (!auth) headers.set("X-FundLex-User", devUser());
    let response;
    try {
      response = await fetch(`${BASE}${path}`, { ...options, headers, cache: "no-store" });
    } catch {
      throw new Error("无法连接本地服务，请确认 FundLex 服务已启动。");
    }
    if (response.status === 401) {
      $("gg-login").hidden = false;
      throw new Error("登录状态已失效，请返回工作台重新登录。");
    }
    let payload = null;
    const type = response.headers.get("content-type") || "";
    if (type.includes("application/json")) {
      try { payload = await response.json(); } catch { payload = null; }
    }
    if (!response.ok) {
      const code = payload?.error_code || payload?.detail || payload?.message || `HTTP ${response.status}`;
      throw new Error(String(code));
    }
    return payload;
  }

  async function init() {
    bindEvents();
    try {
      const cap = await api("/api/capabilities");
      $("gg-identity").textContent = cap.auth_mode === "password" ? "账号登录" : `开发身份：${devUser()}`;
      if (cap.auth_mode === "password" && !token()) {
        $("gg-login").hidden = false;
        return;
      }
    } catch (error) {
      toast(error.message);
    }
    await Promise.all([loadCorpus(), loadRuns()]);
    const requested = new URLSearchParams(location.search).get("run");
    if (requested) await selectRun(requested, true);
  }

  function bindEvents() {
    $("gg-upload-form").addEventListener("submit", uploadRun);
    $("gg-refresh-runs").addEventListener("click", () => loadRuns().catch((e) => toast(e.message)));
    $("gg-reload-run").addEventListener("click", () => selectRun(state.current, true));
    $("gg-engine-btn").addEventListener("click", runEngineCompatibility);
    document.querySelectorAll(".gg-tab").forEach((button) => {
      button.addEventListener("click", () => switchTab(button.dataset.tab));
    });
    $("gg-corpus-refresh").addEventListener("click", () => loadCorpus(true));
  }

  async function loadCorpus(show = false) {
    try {
      const data = await api("/api/guide-generation/corpus");
      const latest = data.latest_snapshot;
      $("gg-corpus").textContent = latest
        ? `${data.contracts} 份合同 · latest ${data.latest_contracts} · 快照 ${String(latest.snapshot_id).slice(0, 14)}…`
        : `${data.contracts} 份合同 · 尚无快照`;
      if (show) toast("Corpus 状态已刷新");
    } catch (error) {
      $("gg-corpus").textContent = "Corpus 状态不可用";
    }
  }

  async function loadRuns() {
    const data = await api("/api/guide-generation/runs?limit=80");
    state.runs = data.items || [];
    renderRuns();
    if (!state.current && state.runs.length) await selectRun(state.runs[0].id, false);
  }

  function renderRuns() {
    const list = $("gg-run-list");
    if (!state.runs.length) {
      list.innerHTML = '<p class="gg-muted">还没有生成任务。上传一份法规开始。</p>';
      return;
    }
    list.innerHTML = state.runs.map((run) => `
      <div class="gg-run-item ${run.id === state.current ? "is-active" : ""}" data-run="${esc(run.id)}">
        <strong title="${esc(run.filename)}">${esc(run.title || run.filename)}</strong>
        <small>${esc(run.status)} · ${esc(run.stage)} · ${new Date((run.created_at || 0) * 1000).toLocaleString()}</small>
      </div>`).join("");
    list.querySelectorAll("[data-run]").forEach((item) => {
      item.addEventListener("click", () => selectRun(item.dataset.run, true));
    });
  }

  async function selectRun(runId, force) {
    if (!runId) return;
    if (!force && state.current === runId && state.detail) return;
    state.current = runId;
    state.detail = null;
    state.requirements = null;
    state.impacts = null;
    state.guide = null;
    state.quality = null;
    state.coverage = null;
    state.residual = null;
    $("gg-empty").hidden = true;
    $("gg-detail").hidden = false;
    renderRuns();
    try {
      state.detail = await api(`/api/guide-generation/runs/${encodeURIComponent(runId)}`);
      renderDetail();
      await loadTab(state.tab);
      schedulePoll();
    } catch (error) {
      toast(error.message);
    }
  }

  function badge(value, extra = "") {
    const text = String(value ?? "");
    const cls = /pass|complete|covered|ready/i.test(text) ? "pass"
      : /fail|failed|gap|unresolved|error/i.test(text) ? "fail"
      : /finding|unresolved|uncertain|with/i.test(text) ? "pass_with_findings" : "";
    return `<span class="gg-badge ${cls} ${esc(extra)}">${esc(text)}</span>`;
  }

  function renderDetail() {
    const run = state.detail;
    const payload = run.summary || {};
    const finalize = payload.finalize || {};
    const stats = run.stats || {};
    $("gg-run-title").textContent = run.title || run.filename;
    $("gg-run-subtitle").textContent = `${run.filename} · Run ${run.id} · 创建 ${new Date((run.created_at || 0) * 1000).toLocaleString()}`;
    $("gg-run-badges").innerHTML = [
      badge(run.status), badge(run.qualification_status), badge(`engine: ${run.engine_status}`),
      badge(`quality: ${(payload.quality || {}).run_status || "not_run"}`),
      badge(`coverage: ${(payload.coverage || {}).run_status || "not_run"}`),
      badge(`residual: ${(payload.residual || {}).status || "not_run"}`),
    ].join("");
    $("gg-run-error").hidden = !run.error_code;
    $("gg-run-error").textContent = run.error_code ? `错误：${run.error_code}` : "";
    const cards = [
      ["法规 Requirements", stats.requirements ?? 0, `modify ${(stats.requirement_dispositions || {}).modify_contract ?? 0}`],
      ["Impact Candidates", stats.impacts ?? 0, `definite ${(stats.impact_statuses || {}).definite ?? 0} / possible ${(stats.impact_statuses || {}).possible ?? 0}`],
      ["Guide Items", stats.guide_items ?? 0, "候选指引"],
      ["Quality Findings", stats.findings ?? 0, `${finalize.critical_quality_findings ?? 0} critical`],
      ["Requirement Gaps", finalize.requirement_gaps ?? "—", "Coverage Gate"],
      ["Unresolved Impacts", finalize.unresolved_impacts ?? "—", "必须有最终去向"],
      ["Latest Contract Uncertain", finalize.latest_contract_uncertain ?? "—", "latest-known 完整性"],
      ["Residual", (payload.residual || {}).saturated ? "saturated" : ((payload.residual || {}).status || "not_run"), `${(payload.residual || {}).calls ?? 0} calls`],
    ];
    $("gg-summary-cards").innerHTML = cards.map(([label, value, hint]) => `
      <div class="gg-stat"><label>${esc(label)}</label><strong>${esc(value)}</strong><small>${esc(hint)}</small></div>`).join("");
    const stages = run.stages || [];
    const order = ["INGEST_REGULATION","EXTRACT_REQUIREMENTS","VERIFY_REQUIREMENTS","BUILD_CORPUS_SNAPSHOT",
      "DISCOVERY_REQUIREMENT_RETRIEVAL","DISCOVERY_CONTRACT_SWEEP","ADJUDICATE_IMPACTS",
      "BUILD_LOCAL_GUIDE_CANDIDATES","MERGE_AND_GENERALIZE","GUIDE_QUALITY_REVIEW","SEMANTIC_COVERAGE",
      "RESIDUAL_MINING","FINALIZE_GUIDE","BUILD_EVIDENCE"];
    const latestByStage = {};
    stages.forEach((step) => { latestByStage[step.stage] = step; });
    $("gg-stage-rail").innerHTML = order.map((stage) => {
      const step = latestByStage[stage];
      const cls = step ? `is-${step.status}` : "";
      return `<span class="gg-stage ${cls}" title="${esc(step?.error_code || "")}">${esc(stage.replaceAll("_", " "))}</span>`;
    }).join("");
    renderOverview(payload, finalize);
  }

  function renderOverview(payload, finalize) {
    const checklist = finalize.checklist || {};
    $("gg-panel-overview").innerHTML = `
      <div class="gg-card">
        <h2>完成清单</h2>
        <ul class="gg-list">${Object.entries(checklist).map(([key, value]) => `<li>${value ? "✓" : "✗"} ${esc(key)}</li>`).join("") || "<li>尚未完成</li>"}</ul>
        <p class="gg-muted">Residual 的结论只能表述为：在当前多路 discovery、full corpus sweep、independent review 和 residual mining 策略下未发现新的 uncovered impact；不是数学意义上的 100% 证明。</p>
      </div>
      <div class="gg-card">
        <h2>Discovery</h2>
        <pre class="gg-details-pre">${esc(JSON.stringify(payload.discovery || {}, null, 2))}</pre>
      </div>
      <div class="gg-card">
        <h2>模型身份</h2>
        <pre class="gg-details-pre">${esc(JSON.stringify(state.detail.model_identity || {}, null, 2))}</pre>
      </div>`;
  }

  function switchTab(tab) {
    state.tab = tab;
    document.querySelectorAll(".gg-tab").forEach((button) => button.classList.toggle("is-active", button.dataset.tab === tab));
    document.querySelectorAll(".gg-tab-panel").forEach((panel) => panel.classList.toggle("is-active", panel.id === `gg-panel-${tab}`));
    loadTab(tab).catch((error) => toast(error.message));
  }

  async function loadTab(tab) {
    if (!state.current) return;
    if (tab === "requirements") return loadRequirements();
    if (tab === "impacts") return loadImpacts();
    if (tab === "guide") return loadGuide();
    if (tab === "quality") return loadQuality();
    if (tab === "coverage") return loadCoverage();
    if (tab === "residual") return loadResidual();
    if (tab === "evidence") return loadEvidence();
  }

  async function loadRequirements() {
    if (!state.requirements) {
      const data = await api(`/api/guide-generation/runs/${state.current}/requirements`);
      state.requirements = data.items || [];
    }
    $("gg-panel-requirements").innerHTML = `
      <div class="gg-card">
        <div class="gg-card-head"><div><h2>Requirement Matrix</h2><p class="gg-muted">每个 Requirement 均有 disposition；unhandled 必须为 0。</p></div></div>
        <div class="gg-table-wrap"><table class="gg-table"><thead><tr><th>ID</th><th>Article</th><th>Disposition</th><th>Requirement</th><th>Source quote</th></tr></thead><tbody>
        ${state.requirements.map((req) => `<tr>
          <td class="gg-mono">${esc(req.requirement_id)}</td>
          <td>${esc(req.article)}</td>
          <td>${badge(req.disposition)}<div class="gg-muted">${esc(req.disposition_reason || "")}</div></td>
          <td>${esc(req.requirement)}<div class="gg-muted">conditions: ${esc((req.conditions || []).join("；"))}<br>exceptions: ${esc((req.exceptions || []).join("；"))}</div></td>
          <td class="gg-quote">${esc(req.source_quote)}</td>
        </tr>`).join("") || '<tr><td colspan="5">尚无要求</td></tr>'}
        </tbody></table></div>
      </div>`;
  }

  async function loadImpacts(page = 1) {
    state.impactPage = page;
    const params = new URLSearchParams({ page: String(page), page_size: "50" });
    if (state.impactReq) params.set("requirement_id", state.impactReq);
    if (state.impactStatus) params.set("status", state.impactStatus);
    const data = await api(`/api/guide-generation/runs/${state.current}/impacts?${params}`);
    state.impactTotal = data.total || 0;
    const reqs = (state.requirements || []).map((item) => item.requirement_id);
    $("gg-panel-impacts").innerHTML = `
      <div class="gg-card">
        <div class="gg-card-head"><div><h2>Impact Overview</h2><p class="gg-muted">所有 definite/possible Impact 必须有最终去向；不会因为聚类消失。</p></div></div>
        <div class="gg-toolbar">
          <select id="gg-impact-req"><option value="">全部 Requirement</option>${reqs.map((id) => `<option ${id === state.impactReq ? "selected" : ""}>${esc(id)}</option>`).join("")}</select>
          <select id="gg-impact-status"><option value="">全部状态</option>${["definite","possible","unlikely"].map((s) => `<option ${s === state.impactStatus ? "selected" : ""}>${s}</option>`).join("")}</select>
          <button class="btn btn-sm" id="gg-impact-refresh">筛选</button>
          <span class="gg-muted">共 ${data.total} 条</span>
        </div>
        <div class="gg-table-wrap"><table class="gg-table"><thead><tr><th>Impact</th><th>Requirement</th><th>Contract</th><th>Status</th><th>Source text / reason</th><th>Disposition</th></tr></thead><tbody>
        ${(data.items || []).map((impact) => `<tr>
          <td class="gg-mono">${esc(impact.impact_id)}</td>
          <td class="gg-mono">${esc(impact.requirement_id)}</td>
          <td class="gg-mono">${esc(String(impact.contract_version_id).slice(0, 18))}…</td>
          <td>${badge(impact.impact_status)}<div class="gg-muted">${esc((impact.discovery_sources || []).join(", "))}</div></td>
          <td>${esc(String(impact.source_text || "").slice(0, 500))}<div class="gg-muted">${esc(impact.impact_reason || "")}</div></td>
          <td>${esc(impact.disposition || "—")}<div class="gg-muted">${esc(impact.disposition_reason || "")}</div></td>
        </tr>`).join("") || '<tr><td colspan="6">尚无影响</td></tr>'}
        </tbody></table></div>
        <div class="gg-pagination"><button id="gg-impact-prev" ${page <= 1 ? "disabled" : ""}>上一页</button><span>第 ${page} 页</span><button id="gg-impact-next" ${page * 50 >= data.total ? "disabled" : ""}>下一页</button></div>
      </div>`;
    $("gg-impact-refresh").addEventListener("click", () => {
      state.impactReq = $("gg-impact-req").value;
      state.impactStatus = $("gg-impact-status").value;
      loadImpacts(1).catch((e) => toast(e.message));
    });
    $("gg-impact-prev").addEventListener("click", () => loadImpacts(page - 1).catch((e) => toast(e.message)));
    $("gg-impact-next").addEventListener("click", () => loadImpacts(page + 1).catch((e) => toast(e.message)));
  }

  async function loadGuide() {
    const data = await api(`/api/guide-generation/runs/${state.current}/guide`);
    state.guide = data;
    const candidate = state.detail?.candidate || {};
    const items = data.items || [];
    $("gg-panel-guide").innerHTML = `
      <div class="gg-card">
        <div class="gg-card-head"><div><h2>Guide Candidate</h2><p class="gg-muted">AI 候选指引。可在下方直接修改字段；保存后系统记录 AI→Human Diff 并重新导出 DOCX。人工版本才是业务最终版本。</p></div>
          <div class="gg-actions"><button class="btn btn-sm" data-download-kind="guide">下载当前 DOCX</button><button class="btn btn-sm" data-download-kind="guide_ai">下载 AI 原版 DOCX</button></div>
        </div>
        <div class="gg-actions gg-candidate-actions">
          <span class="gg-muted">候选状态：${badge(candidate.status || "draft")} · 版本 ${esc(candidate.current_version_no || "—")}</span>
          <button class="btn btn-sm" data-candidate-action="approve" ${candidate.status === "candidate_ready" || candidate.status === "human_draft" ? "" : "disabled"}>批准当前版本</button>
          <button class="btn btn-sm btn-primary" data-candidate-action="publish" ${candidate.status === "approved" ? "" : "disabled"}>发布候选版本</button>
        </div>
        <p class="gg-muted">共 ${items.length} 条 · 人工版本 ${(data.human_versions || []).length} 个 · Guide SHA <span class="gg-mono">${esc(data.guide_sha256 || "")}</span></p>
      </div>
      ${items.map((item) => guideEditor(item)).join("") || '<div class="gg-card">尚无候选指引。</div>'}`;
    $("gg-panel-guide").querySelectorAll("[data-save-item]").forEach((button) => {
      button.addEventListener("click", () => saveGuideItem(button.dataset.saveItem, button));
    });
    $("gg-panel-guide").querySelectorAll("[data-download-kind]").forEach((button) => {
      button.addEventListener("click", () => downloadArtifact(button.dataset.downloadKind, button));
    });
    $("gg-panel-guide").querySelectorAll("[data-candidate-action]").forEach((button) => {
      button.addEventListener("click", () => transitionCandidate(button.dataset.candidateAction, button));
    });
  }

  function guideEditor(item) {
    const id = item.guide_item_id;
    const list = (value) => esc((value || []).join("\n"));
    return `<details class="gg-guide-item" data-item="${esc(id)}">
      <summary><strong>${esc(id)} · ${esc(item.title)}</strong>${badge(item.quality_status)}${badge(item.coverage_status)}${badge(item.new_text_origin)}</summary>
      <div class="gg-guide-body">
        <div class="gg-grid-2">
          <div class="gg-field"><label>Title</label><input data-field="title" value="${esc(item.title)}"></div>
          <div class="gg-field"><label>Section</label><input value="${esc(item.section)}" disabled></div>
        </div>
        <div class="gg-field"><label>Business requirement</label><textarea data-field="business_requirement">${esc(item.business_requirement)}</textarea></div>
        <div class="gg-field"><label>Instruction</label><textarea data-field="instruction">${esc(item.instruction)}</textarea></div>
        <div class="gg-field"><label>Applicability</label><textarea data-field="applicability">${esc(item.applicability)}</textarea></div>
        <div class="gg-grid-2">
          <div class="gg-field"><label>Conditions（每行一条）</label><textarea data-field="conditions">${list(item.conditions)}</textarea></div>
          <div class="gg-field"><label>Exceptions（每行一条）</label><textarea data-field="exceptions">${list(item.exceptions)}</textarea></div>
        </div>
        <div class="gg-field"><label>Old text patterns（每行一条）</label><textarea data-field="old_text_patterns">${list(item.old_text_patterns)}</textarea></div>
        <div class="gg-field"><label>New contract text</label><textarea class="tall" data-field="new_text">${esc(item.new_text)}</textarea></div>
        <div class="gg-grid-2">
          <div class="gg-field"><label>New text origin</label>
            <select data-field="new_text_origin">
              ${["model_drafted","regulation_verbatim","contract_pattern_adapted"].map((origin) => `<option ${origin === item.new_text_origin ? "selected" : ""}>${origin}</option>`).join("")}
            </select>
          </div>
          <div class="gg-field"><label>Evidence</label><div class="gg-muted">${esc((item.impact_ids || []).length)} impacts · ${esc((item.requirement_ids || []).join(", "))} · version ${esc(item.version)}</div></div>
        </div>
        <div class="gg-actions"><button class="btn btn-primary btn-sm" data-save-item="${esc(id)}">保存人工修订</button><span class="gg-muted" data-save-msg="${esc(id)}"></span></div>
      </div>
    </details>`;
  }

  async function saveGuideItem(itemId, button) {
    if (state.saving) return;
    const container = document.querySelector(`details[data-item="${CSS.escape(itemId)}"]`);
    if (!container) return;
    const payload = {};
     container.querySelectorAll("[data-field]").forEach((field) => {
      const name = field.dataset.field;
      if (name === "conditions" || name === "exceptions" || name === "old_text_patterns") {
        payload[name] = field.value.split("\n").map((v) => v.trim()).filter(Boolean);
      } else {
        payload[name] = field.value;
      }
    });
    state.saving = true;
    button.disabled = true;
    const msg = container.querySelector(`[data-save-msg="${CSS.escape(itemId)}"]`);
    if (msg) msg.textContent = "保存中…";
    try {
       payload.expected_current_version_id = state.detail?.candidate?.current_version_id || null;
       const result = await api(`/api/guide-generation/runs/${state.current}/guide/items/${encodeURIComponent(itemId)}`, {
         method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      });
      if (msg) msg.textContent = `已保存，版本 ${result.version_no}`;
      toast(`已保存人工修订（版本 ${result.version_no}）`);
      await loadGuide();
      await selectRun(state.current, true);
    } catch (error) {
      if (msg) msg.textContent = error.message;
      toast(error.message);
    } finally {
      state.saving = false;
      button.disabled = false;
    }
  }

  async function downloadArtifact(kind, button) {
    if (!state.current) return;
    button.disabled = true;
    try {
      const headers = {};
      const auth = token();
      if (auth) headers.Authorization = `Bearer ${auth}`;
      else headers["X-FundLex-User"] = devUser();
      const response = await fetch(`${BASE}/api/guide-generation/runs/${encodeURIComponent(state.current)}/download/${encodeURIComponent(kind)}`, { headers, cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = kind === "guide_ai" ? "generated_guide_ai.docx" : "generated_guide.docx";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      toast(error.message);
    } finally {
      button.disabled = false;
    }
  }

  async function transitionCandidate(action, button) {
    if (!state.current) return;
    button.disabled = true;
    try {
      const versionId = state.detail?.candidate?.current_version_id;
      await api(`/api/guide-generation/runs/${encodeURIComponent(state.current)}/candidate/${action}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ version_id: versionId }),
      });
      toast(action === "approve" ? "候选版本已批准" : "候选版本已发布");
      await selectRun(state.current, true);
    } catch (error) {
      toast(error.message);
      button.disabled = false;
    }
  }

  async function loadQuality() {
    const data = await api(`/api/guide-generation/runs/${state.current}/quality`);
    $("gg-panel-quality").innerHTML = `
      <div class="gg-card"><div class="gg-card-head"><div><h2>Guide Quality Gate</h2><p class="gg-muted">与 Coverage 独立；Engine Compatibility 也不参与这里的判定。</p></div></div>
      <pre class="gg-details-pre">${esc(JSON.stringify(data.summary || {}, null, 2))}</pre></div>
      <div class="gg-card"><h2>Findings</h2><div class="gg-table-wrap"><table class="gg-table"><thead><tr><th>Severity</th><th>Category</th><th>GuideItem</th><th>Description</th><th>Evidence</th></tr></thead><tbody>
      ${(data.findings || []).map((f) => `<tr><td class="gg-severity-${esc(f.severity)}">${esc(f.severity)}</td><td>${esc(f.category)}</td><td class="gg-mono">${esc(f.guide_item_id || "—")}</td><td>${esc(f.description)}<div class="gg-muted">${esc(f.recommendation || "")}</div></td><td class="gg-quote">${esc(f.evidence_quote || "")}</td></tr>`).join("") || '<tr><td colspan="5">无</td></tr>'}
      </tbody></table></div></div>`;
  }

  async function loadCoverage() {
    const params = new URLSearchParams({ limit: "500" });
    if (state.coverageLevel) params.set("level", state.coverageLevel);
    if (state.coverageStatus) params.set("status", state.coverageStatus);
    const data = await api(`/api/guide-generation/runs/${state.current}/coverage?${params}`);
    $("gg-panel-coverage").innerHTML = `
      <div class="gg-card"><div class="gg-card-head"><div><h2>Semantic Coverage Gate</h2><p class="gg-muted">Requirement / Impact / Contract × Requirement / Semantic Applicability 四层。</p></div></div>
      <pre class="gg-details-pre">${esc(JSON.stringify(data.summary || {}, null, 2))}</pre>
      <div class="gg-toolbar">
        <select id="gg-coverage-level"><option value="">全部层级</option>${["requirement","impact","contract_requirement"].map((v) => `<option ${v === state.coverageLevel ? "selected" : ""}>${v}</option>`).join("")}</select>
        <select id="gg-coverage-status"><option value="">全部状态</option>${["covered","disposed","gap","uncertain","unresolved","not_applicable","false_positive","affected","not_affected"].map((v) => `<option ${v === state.coverageStatus ? "selected" : ""}>${v}</option>`).join("")}</select>
        <button class="btn btn-sm" id="gg-coverage-filter">筛选</button>
        <span class="gg-muted">共 ${data.total} 条，展示前 ${(data.items || []).length} 条</span>
      </div>
      <div class="gg-table-wrap"><table class="gg-table"><thead><tr><th>Level</th><th>Ref</th><th>Status</th><th>Reason</th></tr></thead><tbody>
      ${(data.items || []).map((row) => `<tr><td>${esc(row.level)}</td><td class="gg-mono">${esc(row.ref_id)}</td><td>${badge(row.status)}</td><td>${esc(row.reason || "")}</td></tr>`).join("") || '<tr><td colspan="4">无</td></tr>'}
      </tbody></table></div></div>
      <div class="gg-card"><h2>Semantic Applicability 样本</h2><div class="gg-table-wrap"><table class="gg-table"><thead><tr><th>GuideItem</th><th>Clause</th><th>Verdict</th><th>Reason</th></tr></thead><tbody>
      ${(data.applicability || []).map((row) => `<tr><td class="gg-mono">${esc(row.guide_item_id)}</td><td class="gg-mono">${esc(row.clause_id)}</td><td>${badge(row.verdict)}</td><td>${esc(row.reason || "")}</td></tr>`).join("") || '<tr><td colspan="4">未测试</td></tr>'}
      </tbody></table></div></div>`;
    $("gg-coverage-filter").addEventListener("click", () => {
      state.coverageLevel = $("gg-coverage-level").value;
      state.coverageStatus = $("gg-coverage-status").value;
      loadCoverage().catch((e) => toast(e.message));
    });
  }

  async function loadResidual() {
    const data = await api(`/api/guide-generation/runs/${state.current}/residual`);
    $("gg-panel-residual").innerHTML = `
      <div class="gg-card"><div class="gg-card-head"><div><h2>Residual Mining</h2><p class="gg-muted">每轮重新检查 Guide 无法解释的合同内容；连续两轮没有新的 meaningful pattern 才视为 saturation 证据。</p></div></div>
      <pre class="gg-details-pre">${esc(JSON.stringify(data.summary || {}, null, 2))}</pre>
      ${(data.rounds || []).map((round) => `<details class="gg-guide-item"><summary><strong>Round ${esc(round.round_no)} · ${esc(round.status)}</strong>${badge(`${round.new_patterns} new patterns`)}${badge(`${round.new_impacts} new impacts`)}</summary>
        <div class="gg-guide-body"><pre class="gg-details-pre">${esc(JSON.stringify(round, null, 2))}</pre></div></details>`).join("") || '<p class="gg-muted">尚未运行</p>'}
      </div>`;
  }

  async function loadEvidence() {
    const data = await api(`/api/guide-generation/runs/${state.current}/evidence`).catch(() => null);
    const detail = state.detail || {};
    $("gg-panel-evidence").innerHTML = `
      <div class="gg-card"><div class="gg-card-head"><div><h2>Evidence / 导出</h2><p class="gg-muted">Evidence 保留 Regulation → Requirement → Impact → Local Candidate → Merged Guide → Reviewer → Coverage → Residual 的完整追踪链。</p></div></div>
        <div class="gg-actions">
          <button class="btn btn-sm" data-download-kind="guide">Candidate Guide DOCX</button>
          <button class="btn btn-sm" data-download-kind="evidence_json">Evidence JSON</button>
          <button class="btn btn-sm" data-download-kind="evidence_html">Evidence HTML</button>
          <button class="btn btn-sm" data-download-kind="engine_json">Engine JSON</button>
          <button class="btn btn-sm" data-download-kind="engine_html">Engine HTML</button>
        </div>
        ${data ? `<pre class="gg-details-pre">${esc(JSON.stringify(data, null, 2))}</pre>` : '<p class="gg-muted">Evidence 尚未生成。</p>'}
      </div>
       <div class="gg-card"><h2>人工版本与 AI→Human Diff</h2>
        <h3>Human Versions</h3><pre class="gg-details-pre">${esc(JSON.stringify((state.guide || {}).human_versions || [], null, 2))}</pre>
        <h3>Changes</h3><pre class="gg-details-pre">${esc(JSON.stringify((state.guide || {}).human_changes || [], null, 2))}</pre>
       </div>`;
    $("gg-panel-evidence").querySelectorAll("[data-download-kind]").forEach((button) => {
      button.addEventListener("click", () => downloadArtifact(button.dataset.downloadKind, button));
    });
  }

  async function uploadRun(event) {
    event.preventDefault();
    const file = $("gg-file").files[0];
    if (!file) return;
    const button = $("gg-upload-btn");
    const msg = $("gg-upload-msg");
    button.disabled = true;
    msg.textContent = "上传中…";
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("config", JSON.stringify({
        path_b_latest_only: $("gg-latest-only").checked,
        run_engine_compatibility: $("gg-engine").checked,
      }));
      const run = await api("/api/guide-generation/runs", { method: "POST", body: form });
      msg.textContent = `已创建任务 ${run.id}`;
      toast("法规已上传，后台开始生成");
      $("gg-upload-form").reset();
      await loadRuns();
      await selectRun(run.id, true);
    } catch (error) {
      msg.textContent = error.message;
      toast(error.message);
    } finally {
      button.disabled = false;
    }
  }

  async function runEngineCompatibility() {
    if (!state.current) return;
    try {
      await api(`/api/guide-generation/runs/${state.current}/engine-compatibility`, { method: "POST" });
      toast("Engine Compatibility 已排队");
      await selectRun(state.current, true);
    } catch (error) {
      toast(error.message);
    }
  }

  function schedulePoll() {
    clearTimeout(state.pollTimer);
    const run = state.detail;
    if (!run) return;
    if (["queued", "running"].includes(run.status)) {
      state.pollTimer = setTimeout(async () => {
        try {
          state.detail = await api(`/api/guide-generation/runs/${state.current}`);
          renderDetail();
          if (state.tab !== "overview") await loadTab(state.tab);
          schedulePoll();
        } catch (error) {
          toast(error.message);
        }
      }, 4000);
    }
  }

  init().catch((error) => toast(error.message));
})();
