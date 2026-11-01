# 全站走查检查单（FULLSITE CHECKLIST）v1.0-草案待主线审定

> 线别：QA 全站走查线（qa-fullsite-qa）。依据：【总攻开工令】阶段一。
> 用户原话（判定基准，逐字）：「所有开发完之后，要对所有的链路进行检查，我说的是所有，你不要之后又跟我说你有页面没有检查到，绝对不能出现任务bug以及非常卡顿的情况。以及要对所有的页面及子页面截图检查，我说的是所有」
> 拆成可判真假断言：
> - A1「所有页面及子页面截图检查，一个不漏」⇔ 本检查单 §3/§4 每一行均有对应截图文件且走查结论非空（✅/❌/⛔阻塞+原因）。
> - A2「所有链路检查」⇔ §5 生命周期链路 LC-01~LC-08 每条有起止证据（截图+产物 hash/下载核对）。
> - A3「绝对不能出现非常卡顿」⇔ §2 性能阈值表逐项实测，全部 ≤ fail 阈值；>warn 须登记现象与处置。
> - A4「任务 bug 为零容忍」⇔ 走查发现的任务链路问题全部登记（FL 号段向主线申请后落 docs/DETAIL_APPEND_FULLSITE_QA.md），阶段二结束时无未处置的 P0/P1。
> 口径约束：①截图状态以代码实证为准（V1=frontend/compare.html+app.js/compare.js/workspace.js/guide_generation.js；V2=frontend/src/**），两个 explore 子agent 独立枚举交叉核对；②「不确定」项统一收入 §7，不许静默丢弃；③本检查单冻结前为草案，性能阈值表（§2）随本单交主线审定后冻结，作为阶段二唯一卡顿判定依据。

## 1. 环境矩阵与口径

| 环境 | Base URL | 说明 | 实证 |
| --- | --- | --- | --- |
| 生产 V1 | `https://fundlex.club/` | 主实例（fundlex-recall-api，127.0.0.1:8010），FUNDLEX_FRONTEND_VERSION=v1，hash SPA（compare.html） | curl 200，title=FundLex合同修订工作台，挂 status_labels/app/compare/workspace/guide_generation.js |
| 测试 V1 | `https://fundlex.club/test/` | 隔离测试实例（fundlex-test-api:8110），frontend-v1.conf 显式 pin v1 + base=/test | /etc/systemd/system/fundlex-test-api.service.d/frontend-v1.conf |
| 生产 V2 | **未上线**（截至 2026-11-01） | 两实例均未启用 FUNDLEX_FRONTEND_VERSION=v2；`/v2/` 命中 V1 catch-all 307 | curl 实证 307；api.py:1719（V1 is the default workbench again） |
| 本地 V2 | `http://127.0.0.1:<port>/`（vite dev 或 dist+FUNDLEX_FRONTEND_VERSION=v2 本地起服） | V2 走查基线取本地构建（dist 即生产候选物）；阶段二若 V2 已上线则切生产 URL | frontend/vite.config.* / api.py:1742 |
| 鉴权 | password 模式，localStorage `fundlex-auth-token` + `Authorization: Bearer` | 凭据一律走环境变量（FUNDLEX_QA_USER/FUNDLEX_QA_PASSWORD/FUNDLEX_QA_TOKEN），不落盘 | app.js:55/73；client.ts:62 |

入口与深链兼容层（V1，阶段二须逐条 307 核对）：
- `/compare` → 307 `/#compare`；`/guide-generation` → 跳转页（读 ?run=/?id= → `#generation?mode=detail&id=…`，guide_generation.html:10-28）
- `/tasks/<id>` → 307 `/?task=<id>#task`；`/tasks`→`#overview`；`/tasks/new`→`#import`；`/guides`→`#guide`；`/settings`→`#settings`；`/users`→`#users`；未知路径→`#overview`（api.py:1802-1819）
- `?task=<id>` 查询串深链（app.js:773，404/403 → 回 overview + toast）
- `#revision` = `#overview` 别名（app.js:211）；未知 hash → 回 workspace + toast「链接无效或已过期，已回到工作台。」（app.js:209）
- V2：`*` → Navigate /tasks；`/workspace` → /tasks（App.tsx:30-31,48）

## 2. 性能阈值表（【冻结候选】交主线审定；阶段二唯一卡顿判定依据）

测量口径：Playwright Chromium，桌面 1440×900 / 移动 390×844 两档；每采样点跑 3 次取中位数；移动端阈值 = 桌面 ×1.5（四舍五入到百位）。采样前禁用缓存场景与默认缓存场景分开记录（默认记录默认缓存）。指标取自 PerformanceNavigationTiming + 自定义探针：

| 指标 | 定义 |
| --- | --- |
| P-TTFB | responseStart（ms） |
| P-DCL | domContentLoadedEventEnd（ms） |
| P-LOAD | loadEventEnd（ms） |
| P-READY | 自定义「就绪选择器」（每页在 manifest 给定，如列表首行/标题）首次可见时间，自 goto 起算（ms） |
| P-CLICK | 交互点击 → 反馈达成（路由切换完成/弹层可见/视图切换完成）耗时，自 click 起算（ms） |
| P-LTASK | P-READY 后 5s 窗口内主线程 longtask(>50ms) 总耗时（ms，参考指标） |

页面分级：A=轻页（列表/工作台/设置/模型/用户/指引列表）；B=重详情页（任务详情/比对详情/指引生成详情/版本对比）；C=最重页（合同结果报告/修订审阅/比对查看器含大文档渲染）。

| 指标 | A 类 warn / fail | B 类 warn / fail | C 类 warn / fail |
| --- | --- | --- | --- |
| P-TTFB | 800 / 2000 | 800 / 2000 | 800 / 2000 |
| P-DCL | 1200 / 2500 | 1500 / 3000 | 1500 / 3000 |
| P-LOAD | 2500 / 5000 | 3000 / 6000 | 3000 / 6000 |
| P-READY | 3000 / 6000 | 4000 / 8000 | 5000 / 10000 |
| P-CLICK（路由切换/弹层/页签） | 300 / 1000 | 300 / 1000 | 300 / 1000 |
| P-CLICK（重视图切换：word↔classic、版本对比渲染） | — | 800 / 2000 | 800 / 2000 |
| P-LTASK（参考） | 1000 / 3000 | 1000 / 3000 | 1500 / 4000 |

豁免与特殊规则：
- 长任务（提交上传、真实模型处理、生成产物、下载大文件）不套 P-CLICK 硬阈值，但**进度反馈必须在 500ms 内出现**（按钮变「正在上传…」/进度条/Toast），超时即 ❌。
- 轮询页（任务详情/生成详情）测量首屏，不测轮询间隔。
- 任一采样点 3 次中位数 >fail ⇒ 该页「卡顿」成立（A3 ❌）；warn~fail 之间 ⇒ 记 ⚠ 并截图留档。
- 缓存口径：默认 warm（同 URL 预载一次后测第二次）；--cold 场景分开记录（records 带 cache_mode）。
- 环境口径：**阈值判定以生产公网采集为准**；本地 dev 采集仅作对照、不进 A3 判定（results.json 记 base_url 可追溯）。
- P-CLICK 超时按超时值记录（必然超 fail → ❌），不以异常中断该行。
- LCP/INP 列入阶段二增强项（采集链路验证后再入冻结表）。
- 阈值冻结前若需调整：改本表+tools/qa/fullsite/perf_budget.json 同步，commit 注明「待主线审定」。

## 3. V1 检查单（生产主战场；hash SPA，11 顶层视图 + 弹层族）

通用截图要求：每行桌面 1440 + 移动 390 各 ≥1 张；弹层行再补弹层开启特写；命名 `<编号>-<视口>-s<样本>.png`（staged 条目阶段二加状态后缀 `<编号>-<状态>-<视口>.png`）。就绪选择器支持 ready_any：**行级优先、容器回落**（防空容器偷跑，shots.py 记录命中的是哪一支）。前置图例：seed:task=已有修改任务；seed:doc=任务内有已处理合同；seed:cmp=已有比对任务（含完成态）；seed:gg=已有指引生成 run（含多版本）；seed:guide=已上传自定义指引≥2 版；seed:admin=admin 身份；seed:empty=全新空账号/清筛选。

### 3.1 工作台与修改主线

| 编号 | 页面/子页面/状态 | 深链/入口 | 前置 | 就绪选择器（P-READY） | 页级 | 状态分支与必查点 | 走查结论 | 性能实测 | 证据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FS-V1-01 | 工作台-有数据总览 | `#workspace` | 登录 | `#workspace-task-rows tr` | A | 3 业务启动卡、3 统计卡（active/attention/completed）计数与点击联动、任务表、分页；15s 轮询不闪烁 | ☐ | | |
| FS-V1-02 | 工作台-筛选深链组合 | `#workspace?q=&kind=revision|compare|generation&status=active|attention|completed&sort=&date_from=&date_to=&page=` | 登录+多任务 | 同上 | A | 每类 kind×status 至少各打 1 组；非法日期 YYYY-MM-DD 校验；刷新后深链状态还原 | ☐ | | |
| FS-V1-03 | 工作台-空态/加载/错误 | 同上 | seed:empty | — | A | 空「当前条件下没有任务…」；加载「正在读取全部业务任务…」；断网错误态+「请稍后重试。」可恢复 | ☐ | | |
| FS-V1-04 | 合同修改列表（overview） | `#overview`（别名 `#revision`） | seed:task | `#task-rows tr` | A | 工具栏搜索/状态/按指引筛选/排序、chips、分页 20/50/100；选中自动定位首条；筛选与页码 sessionStorage 还原 | ☐ | | |
| FS-V1-05 | overview-新手引导卡 | `#overview` | 清 localStorage 首次 | `#first-run-guide` | A | 三步说明展示与「不再显示」dismiss 持久 | ☐ | | |
| FS-V1-06 | overview-空态/首载失败 | `#overview` | seed:empty / 断网 | — | A | 「当前条件下没有任务」/「任务暂未加载，请检查连接后刷新」；已有数据时失败仅角标 refreshNote 不清屏 | ☐ | | |
| FS-V1-07 | 新建任务（import 新建模式） | `#import` | 登录 | `#dropzone` | A | 拖放/选文件/选文件夹三入口；任务名必填错误 #task-name-error；清单统计 4 KPI；行级替换/移除；本地校验五类 issue（格式/空文件/超限/重复/补传不匹配） | ☐ | | |
| FS-V1-08 | import-提交与上传进度 | `#import` | seed:guide | `#submit-task` | A | 指引绑定读取中/不可用警示卡两态；提交后控件禁用+「正在上传…」+进度条（≤500ms 出反馈）；upload-message 结果说明 | ☐ | | |
| FS-V1-09 | import-补传模式 | 任务详情 #recover-btn → `#import` | seed:task 含未接收文件 | `#cancel-recover` | A | 面包屑变「补传文件」；导出待补传清单 CSV；退出补传返回任务进度 | ☐ | | |
| FS-V1-10 | 任务详情（task） | `#task?id=<taskId>` | seed:task | `#overall-counts` | B | KPI、阶段条（上传/处理）、进度条、任务切换器、暂停 toggle、补传入口；缺 id 时 go() 回填当前任务 | ☐ | | |
| FS-V1-11 | task-逐合同明细六筛选+chips | 同上 | seed:task | `#doc-rows tr` | B | #doc-search 上传/#doc-upload-filter 资格/#doc-qualification-filter 交付/#doc-completeness-filter 处理/#doc-status-filter 原因/#doc-reason-filter + #doc-sort + 分页；筛选无结果文案；失败「合同列表暂未加载，请刷新」 | ☐ | | |
| FS-V1-12 | task-交付文件区 | 同上 | seed:task(终态) | `下载全部 ZIP` 按钮 | B | 下载全部 ZIP/导出结果清单 CSV/结果总览 md 三件可下载且非空；无结果时禁用+toast 解释；暂停时未终态合同显示「已暂停」 | ☐ | | |

### 3.2 比对域（compare.js 子路由）

| 编号 | 页面/子页面/状态 | 深链/入口 | 前置 | 就绪选择器 | 页级 | 状态分支与必查点 | 走查结论 | 性能实测 | 证据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FS-V1-13 | 比对-列表 | `#compare?mode=list&q=&status=&page=` | seed:cmp | `#compare-task-list > *` | A | 搜索/状态筛选/分页 20；空态「当前条件下没有比对任务…」；失败 field-error+原因；列表卡状态/差异数/不完整标注；sessionStorage 恢复上次列表路由 | ☐ | | |
| FS-V1-14 | 比对-新建 | `#compare?mode=new` | 登录 | `#compare-submit` | A | 任务名选填；文件夹配对（相对路径配对提示 N 组/M 未配对）；动态增删行；上传过程三阶段文案；提交反馈 ≤500ms | ☐ | | |
| FS-V1-15 | 比对-新建续传态 | 同上 | 中断的上传草稿 | `#compare-retry` | A | 「继续上传」续传草稿恢复；消息区 #compare-upload-message | ☐ | | |
| FS-V1-16 | 比对-详情框架 | `#compare?mode=detail&id=<taskId>` | seed:cmp | `#compare-pair-list` | B | 任务头加载占位；任务不可用态（「任务不可用」+错误+返回列表）；#compare-pending-note 处理中提示；组 tab 条含状态/差异数/错误 | ☐ | | |
| FS-V1-17 | 比对-查看器 Word 视图（默认） | 同上+选组 | seed:cmp 完成态 | `#compare-word-view` | C | markup all/simple/final 三档；显示源文档开关；修订栏筛选(''/modify/insert/delete)+上下处导航+计数；localStorage 记忆三键 | ☐ | | |
| FS-V1-18 | 比对-人工选择工作流 | 同上 | 同上 | `#compare-selection-save` | C | 选择进度/状态、全部采用 A/B、定位待选择、保存、生成选择结果、问题列表、产物下载；selectionDirty 脏标记 | ☐ | | |
| FS-V1-19 | 比对-双栏对照视图 | detail→data-compare-view-mode=classic | 同上 | `#compare-classic-view` | C | 对齐连线 SVG 渲染；拖宽预览；与 word 互切 P-CLICK≤800/2000 | ☐ | | |
| FS-V1-20 | 比对-移动三窗格/双侧 | 同 17/19，视口 390 | 同上 | 同上 | C | word: merged/left/right（data-word-pane）；classic: left/right（data-compare-side）；记忆键 | ☐ | | |
| FS-V1-21 | 比对-空/错误/不完整三态 | viewer 空态分支 | seed:cmp(处理中/失败组) | `#compare-viewer-empty` | C | 处理中「该组正在处理或等待上传…」；组失败 pairErrorLabel；COMPARE_PAIR_INCOMPLETE 分支文案 | ☐ | | |
| FS-V1-22 | 比对-覆盖不完整气泡 | `#compare-coverage-chip` | 覆盖不完整任务 | `#compare-coverage-list` | C | 点击展开列表、点外自动关闭 | ☐ | | |
| FS-V1-23 | 比对-未保存守卫 | 脏状态离开 | selectionDirty | — | B | go() 原生 confirm「当前有未保存的更改，确认离开此页？」；beforeunload 拦截 | ☐ | | |
| FS-V1-24 | 比对-组深链 | `#compare?mode=detail&id=<taskId>&pair=<pairId>` | seed:cmp | viewer 打开 | C | openPair 直达指定组 | ☐ | | |
| FS-V1-25 | `/compare` 307 兼容入口 | `/compare` | — | — | A | 307 → `/#compare` | ☐ | | |

### 3.3 指引生成域（guide_generation.js，挂 #gg-root）

| 编号 | 页面/子页面/状态 | 深链/入口 | 前置 | 就绪选择器 | 页级 | 状态分支与必查点 | 走查结论 | 性能实测 | 证据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FS-V1-26 | 生成-列表 | `#generation?mode=list&page=&q=&status=queued|running|paused|failed|complete|complete_with_unresolved` | seed:gg | `#gg-list-results` | A | 三种空态文案（当前页无匹配/范围内无/还没有生成任务）；showError+重试块；后端不分页时降级 limit=200 | ☐ | | |
| FS-V1-27 | 生成-新建 | `#generation?mode=new` | 登录 | `#gg-submit` | A | 文件校验（DOCX/带文本层 PDF ≤80MB toast）；任务名只读取文件名；高级选项：语料上限校验错误 #gg-corpus-limit-error、#gg-latest；语料概览加载/失败 note；费用确认勾选门（不勾不可提交） | ☐ | | |
| FS-V1-28 | 生成-详情框架 | `#generation?mode=detail&id=<runId>` | seed:gg | `.gg-*` 任务头 | B | 任务头（状态/候选前检查/当前版本/阶段徽章）；#gg-run-scope 语料上限警示条；runProblem 错误码；重试区 .gg-retry+计数+confirm「确认继续处理此任务？…消耗预算…」 | ☐ | | |
| FS-V1-29 | 生成-tab 总览 overview | `…&tab=overview` | seed:gg | 进度阶段区 | B | 进度阶段；质量/覆盖/补漏/适用性四卡各自空态文案；「尚无完整核验结论…」 | ☐ | | |
| FS-V1-30 | 生成-tab 候选指引 guide | `…&tab=guide` | seed:gg | 条目编辑区 | B | 条目编辑脏标记→离开守卫；批准/发布前原生 confirm；空态「尚无候选指引…」 | ☐ | | |
| FS-V1-31 | 生成-tab 法规依据 requirements | `…&tab=requirements` | seed:gg | 需求列表 | B | 需求列表+合同影响（影响筛选：requirement/status/page 分页）；三空态文案（无要求/无影响/无法读取关联原文） | ☐ | | |
| FS-V1-32 | 生成-tab 待处理问题 issues | `…&tab=issues` | seed:gg | issues 容器 | B | 问题列表与状态流转 | ☐ | | |
| FS-V1-33 | 生成-tab 版本与导出 versions | `…&tab=versions` | seed:gg(≥2版本) | 版本列表 | B | 版本列表；内容对照三空态（无候选/不足两版/无快照/无字段差异）；产物下载空态「尚无可下载产物。」；有产物可下载 | ☐ | | |
| FS-V1-34 | 生成-未登录态 | `#generation` 未登录 | 未登录 | — | A | 整页「请先通过工作台登录，再使用指引生成。」 | ☐ | | |
| FS-V1-35 | 生成-轮询失败警示 | detail 轮询≥3 次失败 | 模拟断网 | 警示条 | B | 「自动刷新已连续失败，已暂停…」+可恢复 | ☐ | | |
| FS-V1-36 | 生成-未保存守卫 | 编辑后离开 | 脏状态 | — | B | hasUnsavedChanges → go() confirm；刷新/读取覆盖前 confirm | ☐ | | |
| FS-V1-37 | `/guide-generation` 跳转页 | `/guide-generation?run=<id>` / `?id=<id>` | — | — | A | 跳转页展示→location.replace 到 `#generation?mode=detail&id=…`，无死链 | ☐ | | |

### 3.4 合同结果与修订审阅（#view-document，detail-overlay 移入整页）

| 编号 | 页面/子页面/状态 | 深链/入口 | 前置 | 就绪选择器 | 页级 | 状态分支与必查点 | 走查结论 | 性能实测 | 证据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FS-V1-38 | 结果报告-完成态 | `#document?id=<taskId>&document=<documentId>` | seed:doc | `#detail-panel` | C | verdict 分支（已完成/需核对例外/不适用/已暂停/正在处理/结果不完整/尚未交付/评测等 9 支）；警示条（评测非正式/需更新目录/遗留任务只读/verification_blocked） | ☐ | | |
| FS-V1-39 | 结果报告-下载区三组九产物 | 同上 | seed:doc(complete) | 下载区 | C | final/selected_final/working_final + redline×3 + report_md/report_json/evaluation_final/evaluation_redline 逐一可下载、非空、hash 与任务记录一致（挂 LC-07） | ☐ | | |
| FS-V1-40 | 结果报告-双栏与判定依据 | 同上 | seed:doc | 「改了哪些条款」 | C | 「改了哪些条款」+「还要人工核」双栏内容；「为什么不处理」判定依据区 | ☐ | | |
| FS-V1-41 | 结果报告-未生成/拉取失败 | 同上 | seed:doc(处理中)/断网 | — | C | 「报告尚未生成，处理完成后可查看。」/「报告暂无法读取，请返回后重试。」 | ☐ | | |
| FS-V1-42 | 修订审阅 tab=review | `…&tab=review` | seed:doc(有修订) | `.rev-item` | C | 修订列表（#/规则号/操作类型/接受勾选，reject 划线）；文档呈现区原文/修改引用框；A/R 快捷键 | ☐ | | |
| FS-V1-43 | 修订审阅-批量与生成 | 同上 | 同上 | `data-action=generate-selected` | C | 全选接受/全拒/生成所选/全部接受（过程文案→完成「接受 N 条，拒绝 M 条」）；下载所选；跨合同上一份/下一份；决定草稿 sessionStorage 还原；生成反馈 ≤500ms | ☐ | | |
| FS-V1-44 | 审阅-加载/失败 | 同上 | 断网等 | — | C | 「正在生成合同呈现与改动清单…」/「无法生成合同呈现，请稍后重试。」 | ☐ | | |
| FS-V1-45 | document-无参空态/深链失效/加载 | `#document` 无参；伪造 id | — | `#document-host` | C | 「请先从修改任务中选择一份合同。[返回修改任务]」；「该合同不存在、无权访问或暂时不可用…」；加载「正在读取合同…」 | ☐ | | |
| FS-V1-46 | document-关闭交互 | `#close-detail`/遮罩/Esc | seed:doc | — | C | 三种关闭均回 `#task?id=`；离开视图自动 closeDetail | ☐ | | |

### 3.5 指引/模型/设置/用户

| 编号 | 页面/子页面/状态 | 深链/入口 | 前置 | 就绪选择器 | 页级 | 状态分支与必查点 | 走查结论 | 性能实测 | 证据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FS-V1-47 | 指引-versions 页签 | `#guide` | seed:guide | `#guide-rows` | A | 当前指引卡（读取中/未确定/已确定三态+flags）；版本表操作（启用/重新解析/下载原件/查看问题/规则开关）；解析中 4s 轮询；恢复内置 #guide-reset-btn | ☐ | | |
| FS-V1-48 | 指引-versions 空/失败 | `#guide` | seed:empty/断网 | — | A | 「还没有可用指引」；失败两档（「当前环境未提供指引配置接口」/「指引列表暂未加载…」） | ☐ | | |
| FS-V1-49 | 指引-diff 版本对比 | `#guide` → diff 页签 | seed:guide(≥2版) | `#guide-diff-card` | B | 基准/对比下拉；规则差异（新增/删除/改动三组+字段级 old→new）；原文比对；视图 merged/side 互切 P-CLICK≤800/2000 | ☐ | | |
| FS-V1-50 | 指引-diff 空态×2+上传卡可及 | 同上 | seed:empty | 上传卡 | B | 「至少需要两个指引版本才能对比…」；「内置指引没有上传的原文文件…」；上传卡 #guide-file/#guide-upload-btn/#guide-upload-message 元素在场可交互（真实上传全流程挂 FS-LC-06/FS-V1-47 启用链） | ☐ | | |
| FS-V1-51 | 指引-rules 规则开关 | `#guide` → rules 页签 | seed:guide | `#guide-rules-inline` | B | 版本下拉→在版本变化时加载；批量全选/全不选；保存成功；「至少保留一条启用规则。」拒绝路径 | ☐ | | |
| FS-V1-52 | 指引-rules 四异常态 | 同上 | 分场景 | — | B | 占位「选择一个版本…」/加载中/404「规则尚未生成…」/未解析「指引解析完成后才能配置…」+读取错误文案 | ☐ | | |
| FS-V1-53 | 指引-详情弹层 #guide-overlay | 「查看问题」/「规则开关」 | seed:guide | `#guide-overlay[open]`(visible) | B | issues/rules 两 mode；Esc/遮罩关+焦点圈定；加载/错误/404 文案；弹层内重新解析按钮 | ☐ | | |
| FS-V1-54 | 模型配置-查看态 | `#models` | 登录 | `#model-settings-body` | A | 来源标注（读取中→我的配置/系统默认）；两角色卡（修改 primary/复核 review） | ☐ | | |
| FS-V1-55 | 模型配置-编辑态全流程 | 同上进入编辑 | 登录 | `data-action=model-settings-save` | A | 系统默认/自己的模型段选；供应商下拉+custom 服务地址；API Key「已保存；留空保留」占位；模型名 datalist；验证连接成功/失败两态；保存/取消；复制 primary→review | ☐ | | |
| FS-V1-56 | 模型配置-异常与确认 | 同上 | 分场景 | — | A | 恢复系统默认 confirm；旧配置警示卡；密钥读取错误文案 | ☐ | | |
| FS-V1-57 | 设置-账户+飞书状态卡 | `#settings` | 登录 | `#settings-current-user` | A | 修改密码入口（dev 身份禁用 tooltip）；飞书状态徽章与文案读取中→已绑定/未绑定；刷新 | ☐ | | |
| FS-V1-58 | 设置-飞书扫码绑定 | `#feishu-oauth-btn` | 未绑定 | `#feishu-oauth-panel` | A | 二维码面板（#feishu-oauth-qr/message/link）；轮询绑定成功态 | ☐ | | |
| FS-V1-59 | 设置-飞书解绑内联确认 | `#feishu-unbind-btn` | 已绑定 | `#feishu-unbind-confirm` | A | 内联二次确认（非弹层）确认/取消两径 | ☐ | | |
| FS-V1-60 | 设置-飞书自建应用向导 4 步 | `#feishu-app-entry` | 登录 | `#feishu-app-wizard` | B | 4 步指示器；panel2 表单校验 #feishu-app-error；panel3 四项能力检查+复制权限清单+重新检测+#feishu-app-recheck-error；panel4 绑定码（复制/换一个/完成态）；查看配置状态/移除应用；3s 轮询 | ☐ | | |
| FS-V1-61 | 用户管理 | `#users` | seed:admin | `#user-rows` | A | 账号表加载/空「当前没有可显示的账号」/失败；禁用/启用 toast；本人行「当前登录账号」无操作 | ☐ | | |
| FS-V1-62 | 用户-新建表单 | 同上 | seed:admin | `#user-create-btn` | A | 本地校验（3 位用户名/字符集/8 位密码 #user-create-error）；409「该用户名已存在。」；member/admin 角色 | ☐ | | |
| FS-V1-63 | 用户-非 admin 拦截 | 直接 `#users` | 非 admin | — | A | 强制回 workspace；导航 #nav-users 隐藏 | ☐ | | |

### 3.6 V1 全局弹层族与入口深链

| 编号 | 对象 | 入口 | 前置 | 就绪选择器 | 页级 | 必查点 | 走查结论 | 性能实测 | 证据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FS-V1-64 | 帮助中心 #help-overlay | 页脚「帮助中心」 | — | dialog 可见 | A | 打开/Esc/遮罩/✕ 关闭；焦点圈定；P-CLICK≤300/1000 | ☐ | | |
| FS-V1-65 | 登录/注册弹层 #login-view | 未登录/401 | 未登录 | `#login-form` | A | 登录错误 #login-error；注册开关开/关两态（#register-hint + #register-form 4 字段+#register-error）；登录成功解锁 .app inert；401 会话失效文案；登出 toast | ☐ | | |
| FS-V1-66 | 修改密码弹层 #password-view | 顶栏/设置页入口 | 登录(password) | `#password-form` | A | 旧/新/确认校验 #pwd-error；错误与成功两径；Esc 关 | ☐ | | |
| FS-V1-67 | 消息中心下拉 | 顶铃 | 登录 | `#notification-panel` | A | 空态「暂无重要消息」；有未读列表+计数徽标；任务状态变更推送；Esc/点外关 | ☐ | | |
| FS-V1-68 | Toast 三 kind | 任意触发 | — | `#toast` | A | success/error/info 三色；error 同步进消息中心 | ☐ | | |
| FS-V1-69 | 原生 confirm 族 | 各守卫点 | 分场景 | — | B | 覆盖：(a) compare/generation 脏离开；(b) models 恢复默认；(c) gg 重试/批准/发布/弃稿；(d) compare beforeunload | ☐ | | |
| FS-V1-70 | `?task=<id>` 查询串深链 | `/?task=<id>` | seed:task | `#task` 视图 | B | 有效直达任务详情；404/403 → 回 overview + toast | ☐ | | |
| FS-V1-71 | 五连 307 入口+未知路径 | `/tasks`、`/tasks/new`、`/guides`、`/settings`、`/users`、`/tasks/<id>`、任意未知 | — | — | A | 逐条 307 目标正确；未知路径落到 overview | ☐ | | |
| FS-V1-72 | logic-demo.html 演示页 | `/static/logic-demo.html` | — | 页面标题 | A | 可打开、自包含渲染、不挂载工作台（可及性确认，非用户链路） | ☐ | | |
| FS-V1-73 | 未解析 hash 回退 | `#nonexistent` | — | — | A | 回 workspace + toast「链接无效或已过期，已回到工作台。」 | ☐ | | |

V1 合计：**73 行**（11 顶层视图全覆盖：workspace 3 / overview 3 / import 3 / task 3 / compare 13 / generation 12 / document 9 / guide 7 / models 3 / settings 4 / users 3 / 全局 10）。

## 4. V2 检查单（React SPA；基线=本地构建，见 §1）

通用：desktop 1440 + mobile 390；Suspense lazy 三页（Compare×3）各补 1 张加载冒落截图。

### 4.1 鉴权与壳

| 编号 | 页面/子页面/状态 | 路由 | 前置 | 就绪选择器 | 页级 | 状态分支与必查点 | 走查结论 | 性能实测 | 证据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FS-V2-01 | 登录页 LoginPage | `/login`（login_required） | 未登录 | 登录表单 | A | 表单错误提示；登录成功跳 /tasks | ☐ | | |
| FS-V2-02 | 开发身份登录 DevIdentityLogin | `/login`（dev 模式） | dev 环境 | 表单 | A | 仅 dev 模式可及 | ☐ | | |
| FS-V2-03 | auth 引导三态 | 任意 | — | — | A | ready 前全局 Spinner「连接服务」；auth.error ErrorState+重试按钮；login_required 未登录时所有受保护路由落 LoginPage | ☐ | | |
| FS-V2-04 | 重定向三件套 | `/`、`/workspace`、`*`、`/tasks/*` 未知 | — | — | A | / 与 /workspace → /tasks；* → /tasks；深链不白屏 | ☐ | | |
| FS-V2-05 | AppShell 壳 | 任意受保护页 | 登录 | 导航区 | A | 导航项齐全；帮助中心 dialog（唯一 role=dialog）开/关；通知下拉空态/有通知+点击跳 `/tasks/<taskId>` | ☐ | | |

### 4.2 任务主线

| 编号 | 页面/子页面/状态 | 路由 | 前置 | 就绪选择器 | 页级 | 状态分支与必查点 | 走查结论 | 性能实测 | 证据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FS-V2-06 | 任务列表 TasksPage | `/tasks` | seed:task | 任务行 | A | 统计卡空态「还没有处理中的任务。」；清单空「没有符合筛选条件的任务。/还没有任务。」；加载 Spinner+「读取中…/刷新中…」；ErrorState | ☐ | | |
| FS-V2-07 | 新建任务 NewTaskPage | `/tasks/new` | 登录 | dropzone | A | dropzone 空态文案；上传进度 <progress>+「上传中…」（反馈 ≤500ms）；form-error 三处（指引/表单/拒收） | ☐ | | |
| FS-V2-08 | 任务详情索引 TaskDetailIndexPage | `/tasks/detail` | 登录/空 | 列表 | A | 「当前没有可查看的任务。」；Spinner；ErrorState | ☐ | | |
| FS-V2-09 | 任务详情 TaskDetailPage | `/tasks/:taskId` | seed:task | 任务头 | B | 「任务不存在。」；LoadingCard；文档表「没有符合条件的合同。」；行级 form-error；控制区错误；文档行跳 report/detail/review 三径 | ☐ | | |
| FS-V2-10 | 合同结果报告 DocumentDetailPage(report) | `/tasks/:taskId/documents/:documentId/report` | seed:doc | 报告区 | C | 合同不存在(L217)；无修改明细/无待核/下载区空；文档/报告双 ErrorState；「下载中…」反馈 | ☐ | | |
| FS-V2-11 | 合同详情 DocumentDetailPage(detail) | `…/detail` | seed:doc | 详情区 | C | 同组件另一分支；与 report 差异化内容核实 | ☐ | | |
| FS-V2-12 | 修订复核 ReviewPage（两别名） | `…/revisions`、`…/review` | seed:doc | 修订面板 | C | 「合同找不到」；「无可复核修订内容」；文档/修订双 ErrorState；message 条；接受/拒绝交互 | ☐ | | |

### 4.3 指引/设置/用户

| 编号 | 页面/子页面/状态 | 路由 | 前置 | 就绪选择器 | 页级 | 状态分支与必查点 | 走查结论 | 性能实测 | 证据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FS-V2-13 | 指引列表 GuidesPage | `/guides` | seed:guide | 列表区 | A | 当前指引空/我的指引空（双 Spinner）；行内 form-error；上传 input | ☐ | | |
| FS-V2-21 | 指引版本对比卡 CompareCard（GuidesPage 内嵌） | `/guides` | seed:guide(≥2版) | 对比卡 | B | 两版本选择联动；规则差异（useGuideDiff）与原文差异（useGuideTextDiff）两内容；加载/错误分支；与 V1 FS-V1-49 同族对照（Guides/index.tsx:147, CompareCard.tsx） | ☐ | | |
| FS-V2-14 | 指引详情 GuideDetailPage | `/guides/:guideId` | seed:guide | 详情区 | B | 「指引不存在。」；LoadingCard；无规则/不可编辑两态 | ☐ | | |
| FS-V2-15 | 设置 SettingsPage | `/settings` | 登录 | 设置区 | A | capabilities ErrorState；绑定错误/密码 message 条 | ☐ | | |
| FS-V2-16 | 模型配置 ModelSettingsPage | `/models` | 登录 | 配置区 | A | 「正在读取模型配置…」；ErrorState；验证连接成功/失败；3× window.confirm（恢复默认等） | ☐ | | |
| FS-V2-17 | 用户 UsersPage | `/users` | seed:admin | 账号表 | A | 「暂无账号。」；ErrorState；LAST_ADMIN 保护 form-error | ☐ | | |

### 4.4 比对域（lazy Suspense 三页）

| 编号 | 页面/子页面/状态 | 路由 | 前置 | 就绪选择器 | 页级 | 状态分支与必查点 | 走查结论 | 性能实测 | 证据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FS-V2-18 | 比对列表 CompareListPage | `/compare` | seed:cmp | 列表 | A | 「还没有合同对比任务」空态；Spinner；ErrorState；Suspense fallback「正在加载合同对比」 | ☐ | | |
| FS-V2-19 | 新建比对 CompareNewPage | `/compare/new` | 登录 | 表单 | A | 文件夹×2 选择；message 条；提交反馈 | ☐ | | |
| FS-V2-20 | 比对工作台 CompareTaskPage | `/compare/:taskId` | seed:cmp | 工作区 | C | 处理中提示(L185)；组未就绪(L192)；「两份合同没有文字差异。」/「暂无可呈现内容。」；notice/warning 条；覆盖率 popover；**CompareReader 子态与 V1 同粒度**：word/classic 双视图、markup 三档、diff 筛选+上下处导航、移动端窗格切换 | ☐ | | |
| FS-V2-22 | 新建任务-补传模式 | `/tasks/new?taskId=<taskId>` | seed:task | 补传标题 | A | 标题切「补传合同」；「待补传 N 份」徽标；待补传 CSV 导出（saveBlob）；文件替换输入；提交回任务（NewTask/index.tsx:50-54,190,196；与 V1 FS-V1-09 同族对照） | ☐ | | |

V2 合计：**22 行**（20 条 Route 声明 100% 覆盖：17 有效路由 + 3 重定向并入 FS-V2-04；16 页面组件全覆盖；弹层族并入 FS-V2-05/16/20；`?taskId=` 查询串深链=FS-V2-22）。

## 5. 全生命周期链路（LC；任务全生命周期=用户原话 A2）

| 编号 | 链路 | 起点→终点 | 关键步骤 | 通过判据 | 走查结论 | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| FS-LC-01 | 登录 | 登录页→工作台 | password 登录→token 落 localStorage→工作台首屏 | 登录成功且 token 生效；错误口令有反馈 | ☐ | |
| FS-LC-02 | 上传→提交 | `#import`/`/tasks/new` | 选真实合同（有应改目标）→任务名→提交→上传进度→任务出现 | 任务落库、文件接收状态正确；进度反馈 ≤500ms | ☐ | |
| FS-LC-03 | 解析→处理 | 任务详情轮询 | 上传阶段→处理阶段→终态（complete/complete_with_unresolved/incomplete 如实呈现） | 状态如实、不谎报 complete；暂停/失败可呈现可恢复 | ☐ | |
| FS-LC-04 | 修订审阅 | `#document…tab=review` | 修订列表→逐条接受/拒绝→生成所选→完成 toast | 生成产物实际反映所选（accept/reject 计数一致） | ☐ | |
| FS-LC-05 | 比对 | `#compare?mode=new`→detail→viewer | 建组上传→处理→word/classic 查看→人工选择→生成→下载 | 产物下载齐全、选择数量与产物一致 | ☐ | |
| FS-LC-06 | 指引生成 | `#generation?mode=new`→detail 5 tab | 上传法规→真实模型→候选→批准→发布→版本导出 | 发布后新版本可启用；五 tab 数据链一致 | ☐ | |
| FS-LC-07 | 下载核对 | 任务详情/document 下载区 | final/redline/report_md/report_json/结果清单csv/修改说明csv/总览md/ZIP | 全件可下、非空、docx 可开、哈希与记录一致、内容与报告一致 | ☐ | |
| FS-LC-08 | 错误与权限 | 各深链 | 401 会话失效→重登录；403/404 深链→安慰文案回退；非 admin 访问 #users | 无白屏、无栈泄露、可恢复 | ☐ | |

## 6. 走查执行规范（阶段二）

1. 工具：`tools/qa/fullsite/shots.py`（骨架已随本单交付），manifest=tools/qa/fullsite/manifest.json（与本单编号一一对应），预算=tools/qa/fullsite/perf_budget.json。
2. 凭据：环境变量 FUNDLEX_QA_USER / FUNDLEX_QA_PASSWORD / FUNDLEX_QA_TOKEN；任何文件/日志/screenshot 命名不得含凭据值。
3. 证据根目录：`/tmp/opencode/qa/fullsite/<run-id>/`（shots/ + results.json + PERF.csv + 控制台错误清单 console-errors.json）。控制台出现 error 级日志即该行 ⚠ 起步。
4. 每行必须有结论：✅ / ⚠（可复现瑕疵+证据）/ ❌（bug/卡顿超标）/ ⛔（阻塞+原因）。❌/⛔ 项须先向主线申请 FL 号段再登记 docs/DETAIL_APPEND_FULLSITE_QA.md。
5. 种子数据缺口（seed:*）阶段二开场 30min 内造齐并记录造数脚本路径；造不出来的状态行标 ⛔ 并说明。
6. 同类清零：任何 ❌ 修复后，对其同族状态行全部重打截图验证无同类残留。
7. 覆盖自证：三数相等=**manifest 条目数 == 检查单编号数（103 行）== results.json covered_ids**（每 id 至少一条记录，含 staged 的 ⛔skipped 记录）；截图数按 id×视口×样本另计并在 run 末尾输出 counts.coverage_ok（!=true 即未完工）。

## 7. 不确定项登记（明示，不许静默丢弃）

| # | 不确定项 | 影响 | 阶段二处置 |
| --- | --- | --- | --- |
| U1 | V1 compare viewer 各开关组合由 localStorage 记忆（不在 URL），组合爆炸 | 截图可能落在记忆分支 | 每条目开无痕上下文（清存储）覆盖默认分支，另抽 2 组记忆分支 |
| U2 | V2 `SafeCompareDocument`「暂无可呈现内容」需后端返回空 html，实际可达性未证 | FS-V2-20 子态造数 | 尝试造数，造不出标 ⛔+原因 |
| U3 | V1 generation detail 的轮询失败警示需模拟后端连续失败 | FS-V1-35 | 用 Playwright route abort 注入 |
| U4 | 生产 V2 未上线；阶段二 V2 基线（本地 dist vs 届时生产）取决于开发合并进度 | §1 环境矩阵 | 听主线令定基线，本单两案兼容 |
| U5 | V1 verdict 9 分支中「评测/遗留任务只读/verification_blocked」等低频分支需特定任务状态 | FS-V1-38 | 种子阶段刻意构造；缺失标 ⛔ |

| U6 | V2 Suspense fallback 截图时机不可保证（加载过快） | §4.4 三页 | 阶段二用 Playwright route 延迟注入稳定捕获 |

—— v1.1 草案（qa-fullsite-qa，2026-11-01）：v1.0 经双盲质检（P0×1+P1×9+P2 若干）后整改——登录死代码接上 bootstrap+登录墙判定（未登录=⛔）、verdict 改按中位数重算、P-READY 超时=显式❌、ready_any 行级优先防偷跑、warm/cold 缓存分口径、307 断言、token 不再发请求头（防第三方泄露）、新增 FS-V2-21/22 两处覆盖漏洞、B 类 P-CLICK-HEAVY 补格。随 perf_budget.json/manifest.json 一并**报主线审定冻结**。
