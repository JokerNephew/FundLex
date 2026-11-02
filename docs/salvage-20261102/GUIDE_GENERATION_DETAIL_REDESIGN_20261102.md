# 指引生成·任务详情 彻底重设计：两体系差异地图 + 信息架构（2026-11-02）

开工令 FE-H / 用户外部任务编号 FL-D1017（第 6 条），集中记录条目 **FL-D549**。
用户原话：「配色还有各个组件和其他页面根本不一样…指引生成 › 任务详情一页的方方面面要大改，不要只在原来的格式上小修小补」。

## 0. 范围与禁区

- **唯一改动层**：V1 静态层（`frontend/guide_generation.html|css|js`；工作台共享层 `app.css/app.js/compare.html` 只在确有必要时做加法，不改既有工作台类名语义）。
- **禁区**：后端 API 契约、任务提交（`POST /api/guide-generation/runs`）与轮询（`schedulePoll`/`open`/路由守卫）逻辑不动；DOM id 改动必须同步 JS 引用并回归。
- **功能回归**：完成后跑一次完整指引生成浏览器流程 + 重跑既有生成相关浏览器断言。

## 1. 两体系差异地图（现状）

工作台体系（业务主页/任务详情，`compare.html + app.css`）与指引生成体系（`guide_generation.js + guide_generation.css`）的差异：

| 维度 | 工作台语言（标准） | 指引生成现状（`gg-*`） | 差异判定 |
| --- | --- | --- | --- |
| 详情头 | `.card.card-pad` 头卡：`.section-title > .batch-title(h1.object-title + .badge)` + `.head-actions(btn-sm)` + `.subnote` + `.task-guide-meta`（左橙条信息带） | 裸 `gg-heading`：h1 24px + 右上角「刷新」大按钮 + `gg-task-status` 文字贴片行 + `gg-retry` 白条卡 | **结构/密度/卡片边界完全不同** |
| 状态徽章 | `.badge b-green/b-red/b-blue/b-amber/b-gray`（4px 圆角、11px 700、五色语义） | `.gg-badge gg-success/warning/error/neutral`（5px 圆角、600 字重、只有四色，running 无蓝色） | **色板与形制不一致，用户「配色不一样」的直接来源** |
| KPI | 详情页 `compact-kpis.counts-kpis + .mini-kpi`（无边框裸排，label 11px muted / b 20px） | `.gg-metrics > .gg-metric`（带边框 8px 卡片，strong 24px） | **有无边框、字号两体系** |
| 阶段进度 | `.stage-rail > .stage-tile`（大格，`current` 橙底高亮）+ `.progress-line + .legend` | `.gg-stages` 15 格小 li（6px 边框、`is-current` 橙框） | **组件层级不同；15 步平铺信息密度过均** |
| Tab | 工作台页内业务 tab 无统一组件（workspace 为 `.business-tabs` 药丸按钮组） | `.gg-tabs` 下划线橙 tab | 需对齐，不等于可小修 |
| 表格/工具栏/分页 | `.toolbar(.searchbox + .control-select)`、`.table/.table-wrap`、`.pagination`（两端对齐+共N条+每页选择） | `.gg-toolbar/.gg-table(th #fafbfc)/.gg-pagination(右对齐)` | **三件套各自为政** |
| 便签/警告 | `.scope-callout`（左橙条米白）/`.task-guide-meta` | `.gg-note` 黄底圆角（#fffbf5/#e8ddcd 硬编码） | **同义异构、硬编码色值** |
| 证据引用 | `.evidence.quote`（白底圆角 + quote-label 小字） | `.gg-quote`（左 3px 灰条 #f7f9fb） | **两版引用样式** |
| 卡片 | `.card`（shadow + radius 10px + card-pad 18/20px） | `.card.gg-card`（padding 20px、无 shadow 变化、margin 16px） | 间距体系不同 |
| 元数据清单 | `dl.task-guide-meta`/表格内小字 | `.gg-meta` 115px 标签列 dl | 对齐方向不同 |
| 版本链/附件 | — | `.gg-version-chain/.gg-diff-columns` | 无对照组件，按工作台卡片语言重排 |

根因结论：指引生成页面自造了一套并列的组件体系（gg-*），只在按钮上复用了 `.btn`；这不是「小修小补」能消除的差异，需要把头卡结构、徽章、KPI、阶段、三件套（toolbar/table/pagination）、便签、证据引用、栅格全部改挂到工作台设计语言上。

## 2. 现状截图档（重设计前基线）

`docs/screenshots/gg-redesign-20261102/before/`（存根 API 本地拍摄，无任何模型/Worker 调用）：

- 工作台参照：`wb-01-workspace.png`、`wb-02-task-detail.png`、`wb-03-task-detail-390.png`
- 指引生成：`gg-01-list.png`、`gg-02-new.png`、`gg-03-detail-running.png`、`gg-04-detail-failed.png`、`gg-05~09-detail-complete-{overview,guide,requirements,issues,versions}.png`、`gg-10-detail-complete-overview-390.png`

## 3. 重设计信息架构（与工作台同语言）

设计原则：先结构（卡片区隔）后组件（workbench 原语），gg-* 只保留业务语义修饰，不再自造形制；所有交互/数据流不变。

### 3.1 任务详情页（主战场）

```
.card.card-pad（头卡）
├─ .section-title > .batch-title: h1.object-title + [任务 .badge b-*] 右侧 .head-actions
│   （刷新 btn-sm；failed/paused 且 can_resume → 「继续处理/重试」btn-sm btn-primary）
├─ .subnote（法规文件名 · 更新时间）
├─ .task-guide-meta 信息带：候选门禁/当前版本/阶段/处理尝试 x/y（全部 .badge b-* 语言）
├─ corpus_limit → .scope-callout；error_code → 红色提示条（卡片内，不再外挂白条）
│
页内 tab（挂工作台语言的药丸式 .business-tabs 同款：.tab-row，列表/详情通用）
│
├─ 总览
│   ├─ compact-kpis.counts-kpis × 4：法规要求 / 合同影响 / 候选条目 / 关键质量问题
│   ├─ 卡「处理进度」：语义 5 段 stage-rail（读取法规→影响发现→判定→起草归并→核验与输出）
│   │   （每 tile：段名 + 该段内已完成/总数 + 当前阶段名徽章），15 真实阶段明细保留为
│   │   tile 网格（workbench tile 形制），不虚构百分比
│   ├─ 卡「候选审阅门禁」：✓/! 双列清单（文字色走 --green/--red tokens）
│   └─ 卡「来源与使用边界」：统一 dl（muted 标签列）
├─ 候选指引：三栏（目录 nav / 编辑 form / 证据 aside），全部 .card；
│   目录条目按钮统一 rev-item 式边框/圆角/hover，激活 = accent-soft；
│   证据引用统一 .evidence.quote 语言；编辑控件沿用工作台输入框 tokens
├─ 法规依据：requirement 明细 = details 卡片行（顶部 badges + 文章名）+ meta dl + quote；
│   影响筛选 = .toolbar(.searchbox 式 select 组)；影响列表同款 details；.pagination 两端对齐
├─ 待处理问题：KPI 行（mini-kpi）+ 质量/覆盖/适用性/补漏/门禁 五个 .card，
│   行级问题 = details 列表；失败读取 = 卡片内红条
└─ 版本与导出：当前版本卡（版本号 chip + 门禁 note + 批准/发布按钮）；
    不可变版本链 = 时间线列表（workbench 卡/分割线语言）；
    版本对照 = 双列 diff（改前灰底 / 改后绿底，沿用工作台 quote-before/quote-after 语义色）；
    授权导出 = .row-actions 按钮行
```

### 3.2 列表页 / 新建页（顺带同语言，同属「方方面面」）

- 列表：`.card.card-pad` 单卡；`.toolbar`（`.searchbox` 搜索 + `.control-select` 状态 + 刷新 btn + ＋新建生成任务 btn-primary.page-primary 右对齐）；`.table/.table-wrap`；`.pagination` 两端对齐。删除 gg-toolbar/gg-table-wrap/gg-pagination 的私有形制。
- 新建：双栏 `.card.card-pad`（法规文件 + 生成前确认），上传区用工作台 `.upload-progress` 语言；成本确认 checkbox + 主按钮仍居 aside；`gg-create` 表单流程、字段 id 不变。

### 3.3 徽章语义映射（gg tone → 工作台 b-*）

- 失败/错误/fail/critical/gap/unresolved/uncovered/not_ready → `b-red`
- 待处理候选/人工草稿/未决/含例外/不确定/可能 → `b-amber`
- 通过/已批准/已发布/已覆盖/已解决 → `b-green`
- 排队/处理中/上传中（running/queued/uploading 类）→ `b-blue`
- 其余中性 → `b-gray`

### 3.4 不改清单（红线）

`window.FundLexGuideGeneration` 接口（`open`/`hasUnsavedChanges`）、全部 `#gg-*` DOM id、`data-gg-*` 行为属性名、`state` 字段与轮询/保存/下载/审批发布流程、`/api/guide-generation/*` 全部请求路径与负载。

## 4. 验收与回归

1. **三态截图断言（新）**：tests/browser 新增重设计断言——running / failed(可续跑) / complete_with_findings 三态下：
   - 头卡存在 `.card .batch-title .object-title` + `.head-actions .btn-sm`；
   - 徽章只出现 `.badge b-*`，不出现 `.gg-badge`；
   - KPI 为 `.mini-kpi`，不出现 `.gg-metric`；
   - 分页为 `.pagination`，表格为 `.table`；
   - 三态各留 1440px 截图（after），390px 各留一张（mobile）。
2. **旧断言改写**：`test_v1_frontend_remediation.py` 中 `.gg-badge/.gg-warning` 两处改为新徽章语言；其余 id/data-attr 断言应原样通过。
3. **功能回归**：`tests/browser/test_guide_generation.py`（完整生成流程：创建→guide 编辑保存→versions）+ 生成相关 V1 回归全绿；`node --check`。
4. self-QA 子代理复核截图 → 登记 FL-D549。

## 5. 记录

- 集中问题记录：FL-D549（本任务，含阶段更新）。
- 现状截图档：见 §2；完工后 after 截图放 `docs/screenshots/gg-redesign-20261102/after/`。

## 6. 实施与验证（2026-11-02 完工）

- 实施：`frontend/guide_generation.css` 整体重写为工作台语言（tokens/组件全复用，gg-* 仅留业务结构修饰）；`frontend/guide_generation.js` 仅渲染层改动——`badge()` 改五色 `.badge b-*`、新增 `STAGE_GROUPS` 5 段聚合、`renderDetailHead` 改头卡语言、列表改 `.toolbar/.table/.pagination`、editor/证据/版本链细节统一。任务提交、PATCH 保存、resume、approve/publish、download、`schedulePoll` 轮询、路由守卫、未保存拦截均原样未动；全部 DOM id 与 `data-gg-*` 行为属性不变。
- 断言与截图：新增 `tests/browser/test_guide_generation_redesign.py`（4 例：running / failed 可续跑 / complete 含门禁 / 列表，含 390px 无横滚断言与 after 截图）；改写 `test_v1_frontend_remediation.py` 旧 `.gg-badge/gg-warning` 断言为 `.badge b-amber`。
- 验证：`test_guide_generation_redesign.py` 4 passed；V1 前端回归 15 passed、指引生成完整流程 1 passed（合计 19 passed，FUNDLEX_BROWSER_TESTS=1）；`node --check`、`git diff --check` 通过；13+4 张 after 截图无页面错误。
- 独立 QA（子代理）：PASS，仅 P2 三条（截图页脚版本串→已重出图、KPI 提示收敛到 title=工作台同款 by design、死样式→已删）。
- 边界：未测生产真实指引生成任务（需真实模型与 Worker，不在本轮 UI 重设计范围）；对照 wb-02 即工作台任务详情存根截图。
