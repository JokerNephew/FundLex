# 前端「处理进度」与「合同结果」合并方案（v2：单表全列常显）

创建：2026-10-15。状态：**已实施并已通过真实浏览器验证**（用户已选择"一张表 + 全部列常显"）。
关联：`frontend/index.html`、`frontend/app.js`、`frontend/app.css`；项目规定见 `AGENTS.md`，细节问题集中登记 `docs/DETAIL_ISSUES_AND_RESOLUTIONS.md`（见 FL-D086）。
本文替代同日 v1（视图切换版）；v1 的选择已由用户否决，结论保留在本文件 §2 变更记录。

> **实施结果（2026-10-15）**：按本方案完成，改动仅 3 个前端文件（无后端/数据库/引擎改动）。
> 已用真实 Chromium（Playwright）驱动真实页面 + 真实接口完成验收：0 页面/控制台报错，表头 7 列全部可见，数据行 7 单元格，空态 `colspan=7`，筛选参数真实下发，分页使用 `doc`，两组统计正常填充。
> 验证脚本：`/tmp/opencode/browser_accept.py`、`/tmp/opencode/browser_accept2.py`。

## 0. 问题与结论

用户观察：侧边栏「处理进度」和「合同结果」两个页面几乎一样。

**核实结论（有代码证据）**：

- 两页**消费同一个后端接口** `GET /api/tasks/{id}/documents`（`fundlex/api.py:720`）。结果页只是多传 `eligibility` / `delivery_status` / `error_code` 三个可选过滤参数（接口本就支持）。
- 两页**共用**同一个任务选择器渲染循环（`app.js:114`）、同一个详情弹窗 `showDetail`、同一个分页组件、同一个 `loadDocuments()`（用 `view==='results'?…:…` 三元分支区分列与筛选）。
- 差异只有三处：表格列、工具栏筛选器、页头按钮。

**结论**：两页不是两个功能，是**同一实体（任务详情）**。合并为**一个「任务详情」页面**，用**一张表**，**全部列常显**，用筛选器聚焦；页头同时提供运行操作与交付操作。保留全部能力，消除双份前端逻辑。

## 1. 目标与非目标

### 目标
1. 侧边栏由「处理进度」「合同结果」两项变一项「任务详情」（`data-nav="task"`）；总览页英雄区两个按钮合并为一个。
2. **一个页面、一张 `<table>`、一套固定表头**。列全部常显，不做视图切换、不做列隐藏。
3. 保留全部现有能力：暂停 / 恢复、补传入口、刷新、下载 ZIP、导出 CSV、下载汇总、资格/交付/原因筛选、目标计数 chip、详情弹窗、分页、排序、行置灰。
4. 消除重复的 `progress*` / `result*` 双份 DOM 与 JS 分支。

### 非目标（明确不做，避免错改）
- **不改后端**：`/api/tasks/{id}/documents` 的过滤参数、`/api/tasks/{id}/download/all`、下载/汇总接口均不变。
- **不改下载/报告/证据内容**与 `showDetail` 逻辑。
- **不改持久任务/DOCX/引擎**任何行为。
- **不引入前端框架或构建步骤**：保持原生 HTML/CSS/JS。
- **不做**：视图切换按钮、列切换、双表头、双表格。

## 2. 关键设计决策

### 决策 A：单表全列常显
固定 6 列：**合同文件 / 上传状态 / 资格 / 交付完整性 / 处理状态 / 业务提示**（+ 操作列）。
理由：用户明确选择；交互最简单，无"视图"概念，任何状态下所有信息都在一屏（窄屏横向滚动）。

代价与对策：
- 列变多 → 窄屏更挤：保留现有 `.table-wrap{overflow-x:auto}` + `.table{min-width}` 横向滚动；把「上传状态」列设窄、`min-width` 适当加大（880px 级）。
- 两种状态都显，可能视觉噪音：用**筛选器**聚焦（见决策 C），并保留「已完整且合格」行置灰（`row-muted`），让异常更醒目。

### 决策 B：统一 id 前缀为 `doc-*`，删除旧 `progress-*`/`result-*`
- `state.progressPage/resultPage` → `state.docPage`；`state.progressSize/resultSize` → `state.docSize`；`state.progressDocs/resultDocs` → `state.taskDocs`。
- **已核实的关键约束**：`pagination(name,…)` 由 `name` 派生 `data-page`/`data-pagesize` 与 `state[\`${name}Page\`]/state[\`${name}Size\`]`（`app.js:90/276/282`）。而 **`state.taskPage`/`taskSize` 已被「任务总览」的任务列表占用**（`loadTasks`）。故文档表**必须用 `name='doc'`**（→ `state.docPage/docSize`），**禁止用 `task`**。同理 `data-detail` 统一为 `doc:i` 配合 `state.taskDocs`。

### 决策 C：筛选器（合并为一个工具栏）
| 控件 | id | 作用 |
| --- | --- | --- |
| 搜索 | `doc-search` | 文件名，两页原有 |
| 上传状态 | `doc-upload-filter` | **新增**（原进度页只有处理状态，上传/待补传此前只能看列） |
| 资格 | `doc-qualification-filter` | 原结果页 |
| 交付完整性 | `doc-completeness-filter` | 原结果页 |
| 处理状态 | `doc-status-filter` | 原进度页 `progress-filter` 与结果页 `processing-filter` 合并，选项取并集 |
| 原因 | `doc-reason-filter` | 原结果页，选项由接口动态填充 |
| 排序 | `doc-sort` | 原两页同款 |

- 所有筛选器映射到接口已有参数：`upload_status` / `eligibility` / `delivery_status` / `job_status` / `error_code` / `sort` / `q`（`api.py:721` 已全部支持，**无需后端改动**）。
- 「上传状态」筛选器为新增 UI，直接复用接口既有 `upload_status` 参数。

### 决策 D：页头按钮全部保留
同一页头并排显示：刷新 / 暂停|继续 / 补传未接收文件 / ↓下载全部结果 ZIP / 导出结果清单 CSV / ↓下载任务汇总 .md。
- 运行类（暂停/补传）与交付类（下载/导出/汇总）按钮的 `disabled` 逻辑照旧（`renderTask` 中已有）。
- 统计区：两个统计块（`overall-counts` 运行口径、`result-counts` 资格/交付口径）**都显示**，不再二选一。

### 决策 E：行置灰
保留 `row-muted`：`job_status==='succeeded' && delivery_status==='complete' && eligibility==='eligible'` 的行置灰，让异常优先。此为既有规则，原仅在结果页；合并后常显（合理）。

## 3. 页面结构（合并后）

```
<section class="section" id="view-task" aria-label="任务详情">
  <div class="task-picker"><label>当前任务 <select id="task-select"></select></label></div>

  <!-- 卡片 1：任务总览 -->
  <div class="card card-pad">
    标题行：#selected-task-title + #task-status + #task-ruleset
    head-actions: 刷新状态 / 暂停任务 / 补传未接收文件
                  / ↓下载全部结果ZIP / 导出结果清单CSV / ↓下载任务汇总.md
    子行：#selected-task-subtitle
    运行统计：#overall-counts（mini-kpi）
    stage-rail（task-upload-label / task-process-label）+ #task-percent + #task-overall-label
    进度条：#overall-progress + legend
    交付口径说明：#doc-scope-note（scope-callout）
  </div>

  <!-- 卡片 2：逐合同表（pagination name = 'doc'） -->
  <div class="card card-pad">
    标题：#doc-scope
    工具栏：#doc-search + #doc-upload-filter + #doc-qualification-filter
            + #doc-completeness-filter + #doc-status-filter + #doc-reason-filter + #doc-sort
    <table class="table" style="min-width:980px">
      thead: 合同文件 | 上传状态 | 资格 | 交付完整性 | 处理状态 | 业务提示 | （操作）
      tbody #doc-rows
    交付三态统计：#result-counts（batch-count，可放表上方或卡1）
    #doc-empty（空态）
    分页 #doc-pagination
  </div>
</section>
```

> 注：`#result-counts`（资格/交付口径）与 `#overall-counts`（运行口径）都保留显示，位置建议：运行口径放卡片 1，交付口径放卡片 2 表头下方。

## 4. 逐处改动清单（防漏改）

### 4.1 `frontend/index.html`
| 位置 | 改动 |
| --- | --- |
| 侧边栏 `data-nav="progress"` 与 `data-nav="results"` 两个按钮 | 合并为一个 `data-nav="task"`，文案「任务详情」，图标建议 `i-file` |
| 总览英雄区 `.hero-actions` 的 `data-nav="progress"`/`data-nav="results"` | 合并为一个 `data-nav="task"`「打开任务详情」 |
| 总览「我的处理任务」表头 `data-nav="progress"`「打开任务 ›」 | 改为 `data-nav="task"` |
| `#first-run-guide` 第 3 步 / `.guide-note` 文案「在『处理进度』或『合同结果』查看…」 | 改为「在『任务详情』查看…」 |
| `<section id="view-progress">` 与 `<section id="view-results">` | 合并为 `<section id="view-task">`（结构见 §3），删除另一个 |
| 表头 `<thead>` | 固定 6 列 + 操作列：合同文件 / 上传状态 / 资格 / 交付完整性 / 处理状态 / 业务提示 /（空表头） |
| 文档表相关 id | 统一为 `doc-*`；保留 `overall-counts`/`result-counts`/`pause-btn`/`recover-btn`/`task-upload-label`/`task-process-label`/`task-percent`/`task-overall-label`/`overall-progress`/`selected-task-title`/`selected-task-status`/`selected-task-subtitle` 原名；删除重复的 `selected-progress` 与旧 `progress-task`/`result-task`（并为 `task-select`） |

### 4.2 `frontend/app.js`
| 位置 | 改动 |
| --- | --- |
| `VIEW_TITLES`（L91） | 删 `progress`/`results`，新增 `task:'任务详情'` |
| `go()`（L93） | 白名单加 `'task'`、删 `'progress'/'results'`；`view==='progress'||'results'` → `view==='task'` → `loadDocuments()` |
| `state`（L26） | 删 `progressPage/resultPage/progressSize/resultSize/progressDocs/resultDocs`，改为 `docPage:1`、`docSize:20`、`taskDocs:[]`（**不可用 `taskPage`/`taskSize`**） |
| `renderTask()`（L96–115） | 进度条只更新 `overall-progress`（删 `selected-progress`）；`overall-counts` 与 `result-counts` 都渲染（不再二选一）；任务选择器 `progress-task`/`result-task` → `task-select`；暂停/补传/下载/导出按钮 disabled 逻辑照旧 |
| `deliveryCounts()`（L117） | 改读 `state.taskDocs` |
| `updateDeliveryNote()`（L118） | 目标容器 `doc-scope-note`；文案含交付三态（`deliveryNoteText`） |
| `selectTask()`（L121） | 重置 `state.docPage`、`state.taskDocs`；清空 `doc-scope`；`progress-rows`/`result-rows` → `doc-rows`；`go('progress')` → `go('task')`；`tokens.progress/results` → `tokens.doc` |
| `loadDocuments()`（L124–126） | 重写：无 `view` 参数；**`name='doc'`**；cols 固定 7（6 列 + 操作，`emptyRow` 同步）；`values` 收集全部筛选器（`doc-search`→`q`、`doc-upload-filter`→`upload_status`、`doc-qualification-filter`→`eligibility`、`doc-completeness-filter`→`delivery_status`、`doc-status-filter`→`job_status`、`doc-reason-filter`→`error_code`、`doc-sort`→`sort`）；行渲染固定 6 列（文件 / 上传状态 badge / 资格 badge / 交付 badge / 处理状态 badge / 业务提示 / 操作）；`state.taskDocs` 赋值；`doc-scope` 文案；动态填充 `doc-reason-filter` 选项并保留当前选择 |
| 行渲染（L125） | **删除 `view==='results'?…:…` 三元**；固定输出全部列；`row-muted` 规则保留 |
| `refresh()`（L127） | `['progress','results'].includes(state.view)` → `state.view==='task'` |
| `seal` 提交后（L148） | `go('progress')` → `go('task')` |
| `exportResults()`（L156） | 引用 id 改名：`result-search`→`doc-search`、`processing-filter`→`doc-status-filter`、`result-sort`→`doc-sort`、`qualification-filter`→`doc-qualification-filter`、`completeness-filter`→`doc-completeness-filter`、`reason-filter`→`doc-reason-filter`；CSV 列与内容不变 |
| `resetWorkspace()`（L199） | 清理 `state.docPage`；`result-rows`/`progress-rows`→`doc-rows`；`result-pagination`/`progress-pagination`→`doc-pagination`；`result-scope`/`progress-scope`→`doc-scope`；`result-scope-note`→`doc-scope-note`；输入框/筛选器 id 列表按新 id |
| 事件委托（L276） | `case 'cancel-recover'` 里 `go('progress')` → `go('task')`；`data-page` 分支 `name==='result'?'results':'progress'` → `'doc'`；`data-detail` 的 `state[\`${name}Docs\`]` → `state.taskDocs` |
| `changed()`（L278） | `name==='result'?'results':'progress'` → `'doc'` |
| 搜索输入绑定（L279） | `progress`/`result` 两项合并为 `doc`；token 分支同步 |
| 筛选器/排序绑定（L280） | `progress`/`result` 两组合并为 `['doc',['doc-upload-filter','doc-qualification-filter','doc-completeness-filter','doc-status-filter','doc-reason-filter','doc-sort']]` |
| 任务选择器绑定（L281） | `['progress-task','result-task']` → `['task-select']` |

### 4.3 `frontend/app.css`
| 位置 | 改动 |
| --- | --- |
| L40–42 `#result-rows tr.row-muted …` | 选择器改为 `#doc-rows tr.row-muted …`（3 条） |
| L28 `#result-scope-note` | 改为 `#doc-scope-note` |
| 表宽 | 文档表 `min-width` 提到 ~980px（多两列）；`.table-wrap` 横向滚动已有，无需新增 |
| 工具栏 | 筛选器变多：`.toolbar{flex-wrap:wrap}` 已有；窄屏 `.control-select{flex:1 1 125px}` 已有，可能需调 `flex-basis` 略小以便一行放更多。可选微调 |

### 4.4 文档
- `docs/ACTIVE_HANDOFF.md`：新增本轮断点（合并、改动文件、验证方式）。
- `docs/DETAIL_ISSUES_AND_RESOLUTIONS.md`：新增 FL-D 条目（两页重复的维护风险 + 合并处理 + 顺手修正的 `emptyRow` 列数瑕疵），编号先查重。
- 历史文档（`docs/TASK_PLAN_UX_AND_APPEND_20261015.md`、`docs/archive/**`、`workbench/*.html`）不动，保留历史。

## 5. 需要重点核对的"易错点"（防错改/漏改）

1. **`data-detail` 索引**：原 `state.progressDocs`/`state.resultDocs` 双数组；合并后仅 `state.taskDocs`，`data-detail` 统一为 `doc:i`，否则点详情取错数组 → 空白/报错。
2. **分页键名**（已核实）：文档表必须 `name='doc'` → `state.docPage/docSize`；**不得用 `task`**（与任务列表 `taskPage/taskSize` 冲突）。`state.docSize` 需同时进入初始 state 与 `resetWorkspace`。
3. **`emptyRow(cols)` 列数**：固定 7（6 列 + 操作），与表头一致。现状 `cols=7` 与旧表头列数不符，本次一并纠正；`selectTask`/`resetWorkspace` 内占位 `emptyRow(5)/(6)/(7)` 全部对齐为 7。
4. **`row-muted`**：合并后常显，规则不变（`succeeded`+`complete`+`eligible`）。确认不会把"运行中"行置灰。
5. **`doc-reason-filter` 选项**：仍由接口 `reason_options` 动态填充，且**保留用户已选值**（原逻辑在 `loadDocuments` 内，照搬）。
6. **通知跳转**：`monitorTasks`/`refresh` 的"查看任务"→ `selectTask(id)` 默认 `navigate=true` → `go('task')`；确认无残留 `go('progress')`/`go('results')`。
7. **`#release-notice`**：结果页原有隐藏 span，合并后保留。
8. **无障碍**：`aria-label` 文案「处理进度」「合同结果」→「任务详情」；筛选器补 `aria-label`；`select` 保留 label。
9. **JS 语法校验**：本机**无 `node`**（`command not found`）。改用浏览器实际加载 + 人工核对；断点中**如实说明未做 `node --check`**，不得虚构通过。
10. **UI 无自动化测试**：`tests/` 中无任何前端 DOM 引用（已核对）。必须**手动浏览器验收**（§7），不能只靠单测。

## 6. 实施步骤（顺序）

1. 改 `index.html`：合并两个 section 为 `view-task`；合并导航与英雄区按钮；固定 6 列表头；统一 id 为 `doc-*`。
2. 改 `app.js`：按 §4.2 逐条改（先 state/常量，再 renderTask，再 loadDocuments，再事件绑定，最后 exportResults/resetWorkspace）。
3. 改 `app.css`：选择器重命名 + 表宽/工具栏微调。
4. 静态核对：全仓搜索残留旧 id（`progress-`、`result-`、`view-progress`、`view-results`、`go('progress')`、`go('results')`、`progress-task`、`result-task`），确保 0 残留（历史文档/workbench/archived 除外）。
5. 浏览器验收（§7）。
6. 更新 `ACTIVE_HANDOFF.md` 与集中问题记录；提交（用户已授权自主判断提交/推送）。

## 7. 验收清单（真实浏览器，非单测）

- [ ] 侧边栏只有「任务详情」一项；总览英雄区只有一个「打开任务详情」。
- [ ] 选择任务后进入任务详情，**一张表**显示全部 6 列。
- [ ] 6 个筛选器（搜索/上传状态/资格/交付/处理状态/原因）+ 排序在**同一张表**上全部生效，可叠加。
- [ ] 分页：翻页、每页数量切换正确（重点核对 `state.docPage/docSize`，确认不与任务列表页码互踩）。
- [ ] 「查看证据/查看状态」详情弹窗打开**正确**合同（重点核对 `data-detail` 索引）。
- [ ] 已完成且合格的行置灰；运行中/异常行不置灰。
- [ ] 导出 CSV 内容与表一致（列含资格/处理/交付/业务提示/原因码）；下载 ZIP / 汇总文件名正确。
- [ ] 暂停/恢复、补传按钮行为不变；补传完成后跳转「任务详情」。
- [ ] 窄屏（≤760px）表格横向滚动正常，筛选器可换行/换行不溢出；控制台无阻断错误。
- [ ] 通知点击"查看任务"能定位到任务详情。

## 8. 风险与回退

- **风险**：id 重命名遗漏导致交互静默失效（无单测覆盖）→ 靠 §5 清单 + §7 逐项点击验收。
- **风险**：多列窄屏拥挤 → 保留横向滚动并实测窄屏。
- **回退**：改动集中在 3 个前端文件，`git revert` 单提交即可；后端零改动，无数据/预算风险。

## 9. 变更记录

- 2026-10-15 建立 v1：两页合并为「任务详情」，表内视图切换（进行中 / 结果）。
- 2026-10-15 v2：**按用户选择改为「一张表 + 全部列常显」**，取消视图切换/列切换/双表头；筛选器由 6 个（新增"上传状态"）统一承载聚焦；页头运行与交付按钮同时显示；两个统计块同时显示。v1 结论作废，本文为准。
