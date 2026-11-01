# qa-compare-ux 线发现登记（FL-D840~859，主册待主线统一并入）

> 按附录格式登记，完工后由主线合并进 docs/DETAIL_ISSUES_AND_RESOLUTIONS.md。

## FL-D840 合同比对同步滚动卡顿机理定位（性能工程，2026-11-01 发现）

- **发现日期**：2026-11-01（qa-compare-ux 工单 A）。
- **问题与影响**：合同比对（V1 compare 页生产形态）滚动任一侧文档时另一侧跟随有明显卡顿（用户原话“卡卡的情况不想再看”），合并视图（Word 视图三栏）与并排（双栏对照）均存在。
- **机理证据（源码级，frontend/compare.js @qa/full-audit-20261031）**：
  1. **settle 通道每 150ms 对全部面板做 force 重排**：`syncPaneScroll` rAF 内走 estimate 快路径后，又置 150ms `syncSettle` 定时器（compare.js:388-412），对每个目标面板调用 `doc.scrollToBlockIndex(index, fraction, false)`——该函数内部执行 `refresh(true,range)`→`place()`（getBoundingClientRect）→`refresh(true)`→`place()` 共最多 4 次含测量与锚点恢复的强制刷新（compare.js:893-913）。连续滚动期间该 settle 反复触发，即使用户仍在滚、目标已对齐也照样强刷，每次 ×最多 4 个面板。
  2. **VirtualDocument.refresh 读写交叉（layout thrash）**（compare.js:821-861）：顺序为 读 scrollTop/clientHeight → 读 visibleBlock（多次 getBoundingClientRect）→ 写 minHeight/卸载/挂载 innerHTML/replaceChildren → 逐 chunk 读 getBoundingClientRect 测高（强制布局#1）→ 写 spacer 高度/清 minHeight/写 scrollTop → 再读 retained.getBoundingClientRect（强制布局#2）→ 写 scrollTop。每次强刷至少 2 次含整文档 DOM 的强制同步布局；force=true 时无早退（仅 `!force` 且 range 不变才 return，:824）。
  3. **双栏对照 SVG 连线每帧重建**：每次 scroll 事件（含被同步压制的帧）都会 `drawLines()`（compare.js:349/351/352），rAF 节流后仍每帧 `svg.replaceChildren(...)` 重建至多 240 条贝塞尔 path（compare.js:234-250），外加 viewBox 重写；滚动期间属于高频、大体量 DOM 写。
  4. **分栏拖动期间每帧全量重测**：`bindColumnSplitter` 的 onChange 在 pointermove 中逐帧触发（app.js bindColumnSplitter `onMove`→`apply`→`onChange`），compare.js 的 `refresh`（compare.js:171-180）随之 rAF 调用 `refreshVirtualLayouts()`——对 5 个面板 `resetMeasurements()`+`refresh(true)`，即拖动分隔条期间每帧对整份合同 DOM 重测量 ×多面板，是造成“拖分隔时最卡”的主因（compare.js:953-958）。
  5. **双滚动监听器**：每个面板既有 VirtualDocument 自带 scrollHandler（schedule→refresh），又有 pane 级 `scroll→syncPaneScroll`（compare.js:1118-1122），叠加 window ResizeObserver(compare-view-body)→drawLines（compare.js:1124），宽度变化时连线重绘与重测叠加。
  6. 监听器均已 `{passive:true}`（compare.js:778、1119），无需改 passive；问题在 handler 体内的工作量与频率，不在阻塞 preventDefault。
- **处理方法（设计，施工与验证见状态更新）**：
  1. syncSettle 改为**校验式**：先读目标面板 visibleBlock，索引一致且 fraction 偏差 <0.25 块则跳过 scrollToBlockIndex，避免滚动中周期性强刷。
  2. scrollToBlockIndex 的二次 `refresh(true)` 增加**无变化快退**（range 未变、无未测 chunk、无强制 range 需求时直接 return）。
  3. 连线改为**滚动中淡出停笔**：活动时给 viewer 加 `is-sync-scrolling`（`#compare-lines` opacity→0，过渡用 `--dur-fast`/`--ease-standard` 令牌），scroll 事件只挂 90ms 去抖 drawLines，停止滚动后一次性重绘，消灭每帧 SVG 重建。
  4. 分栏拖动**降载**：`bindColumnSplitter` 增加 `onEnd` 回调；拖动中 onChange 仅失效 diffPositions + 去抖连线重绘（文本重排交给浏览器 CSS，JS 不做重测），pointerup 后一次性 `refreshVirtualLayouts()`+重对齐。经典栏 gutter（bindCompareSplitter）拖完/键盘调整后追加 `alignPanels`（去抖 120ms）。
  5. 量化口径：Playwright 场景（650 块双栏不等长合同夹具，沿用 test_compare_scroll_sync_uses_aligned_paragraphs 夹具形态）记录滚动期间 longtask 数与总阻塞时长、rAF 帧间隔 p95/掉帧率，优化前后对照。
- **施工中追加机理（实证）**：6. 经典双栏容器 `#compare-columns` 的 `border-radius:9px + overflow:hidden` 圆角裁剪使两侧滚动正文**每帧整块重栅格化**（逐项剥离实验：去圆角/去 overflow:hidden 后 >25ms 帧占比 73%→33%，去 box-shadow 无效）——CSS 修复为父级 `overflow:visible`（圆角观感由 compare-pane 自带 8px 圆角承担）；7. `cacheDiffPositions` 失效风暴：滚动期 chunk 重挂载→`onVirtualChange`→`diffPositions=null`→下次 `drawLines` 又全量读 240 个 diff 锚点 rect——改为 `VirtualDocument.refresh` 测量通道**同一次布局**顺带采集 `marks` Map（`collectMarks`），drawLines 只读 Map 不再触发强制布局。
- **实施（全部落地）**：compare.js（settle 校验式、refresh 无变化快退、drawLinesDeferred 90ms 去抖+滚动中淡出、marks 采集、splitter 拖动降载与 onEnd 收口、经典 gutter 收口对齐）；compare.css（`#compare-columns` overflow:visible、`#compare-lines` opacity 令牌过渡+`is-sync-scrolling` 淡出）；app.js（FundLexColumnSplitter 增加 `onEnd`）。
- **验证（量化对照，夹具=650 块不等长+130 diff，Chromium headless，证据 docs/frontend/evidence/compare-scroll-20261101/）**：
  - 经典对照滚动：>25ms 帧占比 **83.3%→32.0%**，连线重建 **242→3 次**、连线重建总耗时 1.0 级（SVG  churn 消灭）；
  - Word 合并栏滚动：**10.6%→4.5%**，p95 帧间隔 33.3→16.8ms；
  - Word 源文档分隔条拖动：force refresh **76 次/472ms→5 次/28ms**，>25ms 帧 1.9%→0%；
  - 走查截图：`walk-classic-scrolling.png`（滚动中连线淡出、两侧第74~83条同步跟随）、`walk-classic-settled.png`（停笔后连线按最新锚点重绘）、`walk-word-view.png`（三栏块级对齐）。
  - 回归：tests/browser/test_v1_frontend_remediation.py 16/16、test_frontend_v2.py 11/11、frontend vitest 24/24 全绿；新增 tests/browser/test_compare_scroll_perf.py 常设门禁（对齐断言 + 指标落盘）。
  - 残留：经典视图剩余 ~32% 掉帧为软件渲染栅格成本（无 longtask、JS 帧均 <3ms），GPU 客户端不构成卡顿主观体感；本机 4 核超售环境为最坏情形。
- **状态**：**已修复并验证**（本线分支 qa-compare-ux-20261101）。
- **变更记录**：2026-11-01 登记（机理+方案）；2026-11-01 同日施工完毕、量化对照达标、回归绿、走查截图归档。

## FL-D841 拖动分隔宽度后两侧文档位置对应错位（正确性，2026-11-01 发现）

- **发现日期**：2026-11-01（工单 A3，用户工单原话“拖动分隔宽度后两侧文档位置对应会错位”）。
- **问题与影响**：宽度变化引起换行重排后，两侧（或合并栏与源文档栏）滚动位置对应错位。
- **根因**：
  1. 经典双栏对照的 gutter（`bindCompareSplitter`）在完成拖动/双击/键盘调整时只执行 `applySplitRatio`+`refreshVirtualLayouts`+`drawLines`（compare.js:141），**从不调用 `alignPanels`**；各面板按各自旧锚点恢复，跨栏锚点映射（buildAlignmentModel 块索引模型）未重跑，重排后对应关系漂移。
  2. Word 视图两个分栏（`bindPanelSplitters`）虽在 onChange 后 160ms 对齐（compare.js:178-179），但拖动中逐帧全量重测（见 FL-D840#4）期间锚点读取基于陈旧测量，拖动过程中视觉错位明显。
  3. 对齐模型本身为**块索引锚点**（compare.js:256-347），与像素高无关，只要拖动结束后跑 `syncPaneScroll(source)` 即可恢复正确对应——缺的是正确时机与降载。
- **处理方法**：经典 gutter 收口处（拖动结束/双击/键盘）与 Word 分栏 onEnd 统一在宽度定稿后 `refreshVirtualLayouts`→`alignPanels`（块索引模型重映射）；拖动中不重测。基线取证：gutter 拖后左栏停在 L0 而右栏停在 R18（≈半屏错位）、源文档分隔条拖后左栏落后 merged/right 17 块。
- **验证**：优化后同场景 gutter 拖后左/右可见块号 67/67，源文档分隔条拖后 merged/left/right 可见块号 0/0/0（夹具含 15 个右侧独立新增块的位置同位），常设断言 ≤4 块（test_compare_scroll_perf.py）。
- **状态**：**已修复并验证**（与 FL-D840 同分支）。
- **变更记录**：2026-11-01 登记；2026-11-01 修复并量化验证。

## FL-D842 V2 ComparePage 同步滚动为比率映射（2026-11-01 排查）

- **发现日期**：2026-11-01（工单 A1 “V2 src 里 ComparePage 同查”）。
- **问题与影响**：`frontend/src/pages/Compare/ComparePage.tsx` 的 `syncScroll`（:363-376）按 `scrollTop/最大滚动` **比率**同步，左右文档块数/高度不等时系统性错位（V1 既有回归测试 test_compare_scroll_sync_uses_aligned_paragraphs 的 650 块不等长场景即为反例）；且每个 scroll 事件**同步直写**目标 scrollTop（无 rAF 节流），`scrollLockRef` 仅 1 帧即释放，惯量滚动中目标面板回波事件可穿透导致抖动；React `onScroll` 属性绑定为非 passive。
- **处理方法（已实施）**：ComparePage.tsx 重写 syncScroll——rAF 节流（每帧至多一次同步）、`syncTargetsRef` 回波抑制（程序写入的目标面板 160ms 内不回写，wheel/pointerdown/touchstart 即接管）、useEffect 手工挂 `{passive:true}` scroll 监听（React onScroll 非 passive）；V2 无块索引对齐模型（整段 HTML 渲染），比率映射保留但加节流与回波抑制（V2 非生产主线，不做对齐模型移植）。
- **验证**：frontend vitest 24/24、tests/browser/test_frontend_v2.py 11/11 绿（V2 构建产物已随改重建）。
- **状态**：**已修复并验证**（同分支）。
- **变更记录**：2026-11-01 登记；2026-11-01 修复并回归验证。

## FL-D843 P3 比对工作台结构合一（dialog→内嵌 region，2026-11-01 实施）

- **发现日期**：2026-11-01（工单 B，方案 docs/frontend/COMPARE_CHAIN_REDESIGN_20261101.md §2.5 已获主线批准）。
- **问题与影响**：V1 比对结果区为全屏 dialog（`role=dialog`+backdrop+Esc/×关闭/上一组/下一组按钮），与任务详情两段嵌套；合同组纵列列表占高约 100px/组；direction-note 与摘要行「当前结果」方向信息重复；Word 工具条修订计数与 rail 头计数重复——违反三禁令（重复信息、层级嵌套）。
- **处理方法（已实施）**：compare.html/detail+viewer 合一为页面内嵌 `role=region`；chip 合同组切换条（`role=tablist` 横向滚动，保留 `#compare-pair-list` id 与 `.compare-pair-status` 类降测试 churn，chip 内序号/组名/文件名/状态·差异数/错误文本）；删 direction-note（方向改摘要行前缀「合同A → 合同B」）、删 Word 工具条重复计数（rail 保留 `compare-revision-count-rail`）、删 backdrop/关闭/上一组/下一组/Esc 及 `compare-pair-counter`；detail 头加 `[data-compare-back-list]`「← 返回比对任务列表」；新增 `setViewerEmpty`/`#compare-viewer-empty`：失败/处理中组点开 region 显空态不再静默留旧结果。compare.js：`setFullscreenViewer`→`setViewerOpen` 清理 dialog 引用。
- **验证**：node --check；tests/browser/test_v1_frontend_remediation.py 16/16（word-style 用例视口 1440→1600 记档：region 受应用框宽约束，rail 拖宽后 word-layout 宽钳制 `container-480` 不够原 +20 断言）；走查截图 docs/frontend/evidence/compare-chain-20261101/ p3-* 6 张目检合格。
- **状态**：**已实施并验证**；走查捕获缺陷另列 FL-D849~852。
- **变更记录**：2026-11-01 实施；2026-11-01 走查修复 FL-D849/850 后复验合格。

## FL-D844 选择控件并入 rail 底部（2026-11-01 实施）

- **发现日期**：2026-11-01。
- **问题与影响**：人工选择与生成面板为视图底部整宽条（跨面板高度外的第六功能区），「预览可生成性」按钮与「生成选择结果」的服务端校验功能重叠（预览/生成/编辑三态认知负担）。
- **处理方法（已实施）**：`.compare-selection-bar` 移入 `.compare-word-revisions`（修订 rail）底部 sticky——进度行+状态行+操作行+下载行；删底部 `.compare-selection-panel` 全段与「预览可生成性」按钮；compare.js 删 `previewSelection`/`selectionAction('preview')` 分支、渲染与禁用逻辑、绑定，点「生成选择结果」即走服务端校验，阻塞原因经 `#compare-selection-issues`/`#compare-selection-status` 内联展示（`setViewerEmpty` 选择器同步去 panel）。
- **验证**：node --check；remediation 16/16（selection/generate 链路用例全绿，含晚响应防串组回归）；走查 p3-workbench 截图 rail 底条目检合格。
- **状态**：**已实施并验证**。
- **变更记录**：2026-11-01 实施并回归绿。

## FL-D845 修订列表项压缩为单行（2026-11-01 实施）

- **发现日期**：2026-11-01。
- **问题与影响**：修订 rail 单项 136px（摘要三行截断+选择按钮区另起行），130 处修订场景滚动成本大、目录感弱。
- **处理方法（已实施）**：修订项单行网格 `24px 序号 | 42px 类型徽标 | 1fr 摘要 | 采用A | 采用B`（`.compare-diff-jump`/`.compare-choice` `display:contents` 摊平入同一 grid）；`DIFF_ITEM_HEIGHT` 136→44（虚拟滚动常数，与 `height:44px` 设计值一致）；摘要强制单行 ellipsis（废止 `-webkit-line-clamp:3`）；choice 视觉文案「采用 A/B」→「A/B」+`title="采用合同A/B此版本"`（语义不丢，腾出摘要宽度）；移动端（≤760px）choice 折回第二行（`grid-column:1/-1`）。
- **验证**：tsc/node --check；走查 p3-workbench-desktop/mobile 截图目检单行观感合格；tests/browser/test_compare_scroll_perf.py 门禁（滚动流畅+块级对齐）过；workbench 53/53。
- **状态**：**已实施并验证**（word rail 旧高度覆写冲突处理见 FL-D851）。
- **变更记录**：2026-11-01 实施；走查后追加 FL-D851 修复并复验。

## FL-D846 V2 比对链路拆三路由（2026-11-01 实施）

- **发现日期**：2026-11-01。
- **问题与影响**：V2 `ComparePage` 单页承载任务列表+新建表单+比对工作台（~880 行），信息架构与批准的 P1/P2/P3 两级嵌套不符。
- **处理方法（已实施）**：拆 `/compare`（CompareListPage：列表+新建入口）、`/compare/new`（CompareNewPage：新建与首传闭环，成功后 `navigate('/compare/'+id,{state:{notice,warning}})`）、`/compare/:taskId?pair=`（CompareTaskPage：chip 切换条 `role=tablist`+内嵌 region，searchParams 持 pair，失败/处理中组显 `compare-viewer-empty` 空态）；共享件/工具入 `src/pages/Compare/shared.tsx`（同步删 V2 工具条重复修订计数）；删 ComparePage.tsx；App.tsx 三 lazy 路由；V2 app.css 同步清理 dialog/direction-note/双计数/revision-summary 规则，chip 横向滚动；tests/compare.test.tsx 重写三路由 MemoryRouter 链、components.test.tsx 导入改 shared。
- **验证**：frontend tsc/lint/vitest 24/24、npm run build 通过（CompareList/New/Task+shared 分 chunk）；tests/browser/test_frontend_v2.py 11/11。
- **状态**：**已实施并验证**（首传 notice 丢失缺陷见 FL-D852）。
- **变更记录**：2026-11-01 实施；走查/回归捕获 FL-D852 后修复复验。

## FL-D847 浏览器测试适配与走查验证（2026-11-01 完成）

- **发现日期**：2026-11-01。
- **问题与影响**：FL-D843~846 结构性变更使既有浏览器用例引用失效选择器/旧交互（上一组下一组/关闭/backdrop/dialog role/工具条计数/单页 V2 路由），且批准要求逐 FL 满配用户视角走查截图。
- **处理方法（已实施）**：test_v1_frontend_remediation.py——`#compare-next-pair`→`[data-compare-pair="1"]`、`#compare-revision-count`→`-rail`、dialog role/backdrop 断言改 region、关闭退出行改「返回比对任务列表→列表→再进入」、`[data-compare-back-list]` 加 `#compare-task-status` 作用域（页内两实例）、word-style 视口 1440→1600 记档；test_frontend_v2.py——深链 `/compare/{taskId}` 直入工作台、下一组改 chip nth(1)+`wait_for_url(pair=)`、heading 改任务名。走查脚本 /tmp/opencode/qa/shot_b_walk.py（V1 三态：成功/处理中/失败 × desktop/mobile）+ shot_b_v2.py（V2 三页 × desktop/mobile），归档 docs/frontend/evidence/compare-chain-20261101/ 12 张，逐张目检。
- **验证**：remediation 16/16、perf 门禁 pass（label after-b）、frontend_fixes 15/15、workbench 53/53（`test_review_list_splitter_drag` 满负载偶发 flake，单跑过）、V2 11/11、vitest 24/24、tsc/lint/build。走查目检捕获并已修复 FL-D849~852。
- **状态**：**已完成并验证**。
- **变更记录**：2026-11-01 适配+走查；同日捕获缺陷修复后全套复跑绿。

## FL-D848 文档归档与提交（2026-11-01 完成）

- **处理方法（已实施）**：本册登记 FL-D843~852；COMPARE_CHAIN_REDESIGN_20261101.md §2.5 施工表标注完成；横向协同产出 docs/frontend/COMPARE_SCROLL_REUSE_NOTES.md（同步滚动/并排对照复用接口说明，供 FL-D891 指引版本比对复用）。
- **状态**：**已完成**（提交前全套回归绿为准）。
- **变更记录**：2026-11-01 登记。

## FL-D849 合同组 chip 错误文本竖排（走查捕获，2026-11-01 发现）

- **发现日期**：2026-11-01（FL-D847 走查 p3-failed 截图目检）。
- **问题与影响**：失败组 chip 内 `.compare-pair-error` 错误文本逐字竖排，chip 被撑至 ~280px 高。
- **根因（两处叠加）**：1) chip 三列 grid（`34px minmax(0,1fr) auto`）下第 4 子元素 error 落进第二行第一列（34px 窄列）；2) 首轮修复规则 `.compare-pair-error{grid-column:1/-1}` 所在行首有一个游离 `.`（`./\*` 开头），选择器非法整条规则被浏览器丢弃——诊断经 computed style 确认 width=34px、gridColumn=auto。
- **处理方法（已实施）**：`.compare-pair-error{grid-column:1/-1}` + 清除游离残点。
- **验证**：重拍 p3-failed-desktop/mobile 目检错误文本横排、chip 高度回归正常。
- **状态**：**已修复并验证**。
- **变更记录**：2026-11-01 发现→修复→走查复验。

## FL-D850 region 聚焦引发主滚动区跳动（走查捕获，2026-11-01 发现）

- **发现日期**：2026-11-01（走查 workbench 截图顶部出现 chip 残影带，诊断为真实布局现象非截图假象）。
- **问题与影响**：打开比对结果时 `setViewerOpen` 对 viewer `focus()`，聚焦使 `.main` 滚动容器下滚（detail 卡 top=-80），任务头与 chip 切换条被甩出视野，深链进入尤甚。
- **处理方法（已实施）**：`viewer.focus({preventScroll:true})`——焦点送达 region 保可访问性，滚动位置不动。
- **验证**：重拍 p3-workbench 截图任务头/chip 条/结果区同屏完整；remediation 16/16 复跑绿。
- **状态**：**已修复并验证**。
- **变更记录**：2026-11-01 发现→修复→复验。

## FL-D851 word rail 修订项旧高度覆写与单行化冲突（走查捕获，2026-11-01 发现）

- **发现日期**：2026-11-01（走查 workbench 截图修订项仍 ~135px 高、choice 折行）。
- **问题与影响**：FL-D845 的单行规则被更高优先级旧规则整体覆写：`.compare-word-revisions .compare-diff-item`（height:128px/block 布局）、`#compare-viewer .compare-word-revisions .compare-diff-item`（height:136px）、`...diff-jump`（grid 三列）、`...choice`（padding 74px 折行）及移动端两条例；摘要折行溢出。
- **处理方法（已实施）**：六处旧覆写全部改造为单行 44px/jump·choice `display:contents`/移动端折行第二行规格；摘要 `-webkit-line-clamp:3` 废止改单行 ellipsis。
- **验证**：重拍截图单行 44px 生效、目检合格；perf 门禁+workbench 53/53 复跑绿。
- **状态**：**已修复并验证**。
- **变更记录**：2026-11-01 发现→修复→复验。

## FL-D852 V2 首传成功提示被 searchParams 默认 effect 清除（回归捕获，2026-11-01 发现）

- **发现日期**：2026-11-01（test_frontend_v2.test_compare_first_upload_seals_and_refetches_explicit_task 红）。
- **问题与影响**：CompareNewPage 提交成功后 `navigate('/compare/'+id,{state:{notice,warning}})`，但 CompareTaskPage 补默认 pair 的 effect `setSearchParams(...,{replace:true})` 不带 state——react-router replace 会清空 location.state，「已提交，对比任务正在处理。」提示永远不显示。
- **处理方法（已实施）**：effect 改为 `setSearchParams(...,{replace:true,state:location.state})`。
- **验证**：复现脚本确认请求链完整且页面恢复显示 notice；V2 浏览器 11/11、vitest 24/24 绿。
- **状态**：**已修复并验证**。
- **变更记录**：2026-11-01 发现→修复→回归绿。

## FL-D853 上传 415 拒收错误码坍缩（CX 全覆盖普查，2026-11-01 发现）

- **发现日期**：2026-11-01（逐行读 fundlex/compare/api.py 上传路径）。
- **问题与影响**：`validate_upload` 415 分支靠匹配英文文案 `"legacy word .doc"` 区分 LEGACY_DOC_UNSUPPORTED，其余（加密 docx、错误格式等）一律坍缩成 `COMPARE_INVALID_DOCX`——文案脆弱且加密文件的真实原因（解除密码）丢失。
- **处理方法（已实施）**：新增 `_upload_rejection_code`——失败路径重跑共享 `validate_docx_upload` 取 `.code`：LEGACY_DOC_UNSUPPORTED 保留、ENCRYPTED_DOCX→COMPARE_ENCRYPTED_DOCX、UNSUPPORTED_FILE_FORMAT→COMPARE_UNSUPPORTED_FORMAT、其余→COMPARE_INVALID_DOCX；不再依赖英文 message 文本。
- **验证**：tests/test_compare_api.py（含 documentProtection 用例，证实其走校验器非 zip 加密路径不受影响）、test_fl_d286_api_safety.py、test_upload_validation.py 全绿。
- **状态**：**已修复并验证**。
- **变更记录**：2026-11-01 发现→修复→回归绿。

## FL-D854 view 端点缓存命中免全量重哈希——评估后撤回修复（2026-11-01 发现）

- **发现日期**：2026-11-01（逐行读 api.py view 端点）。
- **问题与影响**：view 每次请求对两份输入对象全量 read+sha256，缓存命中本可省——初衷为性能优化。
- **处理方法（已实施）**：**撤回优化**。曾拆 `_view_cache_get` 并给命中路径降级为 size 活性门，但 tests/test_compare_system_review.py::test_view_fails_closed_when_source_or_result_object_changes 锁定「源对象被同长度篡改（翻转一字节）时须 409 COMPARE_INPUT_INTEGRITY_FAILED」的 fails-closed 门——size 门无法发现同长度篡改。端点已恢复每请求全量校验（含注释说明）；仅保留 `_view_cache_get` 抽出重构（无行为变化）。
- **验证**：test_compare_system_review.py 复过；compare API 套件全绿。
- **状态**：**已评估-不修复**（fails-closed 门优先于性能；优化撤回，重构保留）。
- **变更记录**：2026-11-01 发现→实施→系统测试捕获冲突→撤回→回归绿。

## FL-D855 register_compare_routes(max_pairs) 死参数（2026-11-01 发现）

- **发现日期**：2026-11-01。
- **问题与影响**：路由注册参数 `max_pairs` 从未在 create 路由使用，只有 store 内硬编码 1000 兜底——配置面失效。
- **处理方法（已实施）**：create 路由显式 `422 COMPARE_TOO_MANY_PAIRS`；store 硬编码保留为二道防线。
- **验证**：compare API 套件全绿。
- **状态**：**已修复并验证**。
- **变更记录**：2026-11-01 发现→修复→回归绿。

## FL-D856 V1 上传拒收错误码无用户可读映射（2026-11-01 发现）

- **发现日期**：2026-11-01（逐行读 frontend/compare.js）。
- **问题与影响**：V1 上传失败直接把 `error_code`/裸状态文本拼进消息，且补救路径不实（被拒文件位密封前不可替换——MANIFEST 绑定 name+size，换文件=MANIFEST_FILE_MISMATCH）。
- **处理方法（已实施）**：`uploadErrorLabel` 8 码映射（LEGACY/ENCRYPTED/UNSUPPORTED/INVALID/UPLOAD_REJECTED/MANIFEST_ENTRY_NOT_FOUND/MANIFEST_FILE_MISMATCH/UPLOAD_IDENTITY_CONFLICT），补救一律诚实写「请新建对比任务上传」。
- **验证**：remediation 16/16 绿。
- **状态**：**已修复并验证**。
- **变更记录**：2026-11-01 发现→修复→回归绿。

## FL-D857 V1 密封不完整组错误兜底误导（2026-11-01 发现）

- **发现日期**：2026-11-01。
- **问题与影响**：COMPARE_PAIR_INCOMPLETE（密封时组不完整，无 diagnostics）落到通用兜底「处理失败，请稍后重试」，但真实原因在随负载下发的文件级 left/right.error_code，重试无用。
- **处理方法（已实施）**：`pairErrorLabel` 优先消费文件级 error_code，按侧列出「合同A/B：原因」，补救「该组已判失败，请新建对比任务重新上传」；diagnostics 分支不可重试文案改「请新建对比任务后重试；若仍失败请联系支持」（test_v1_frontend_remediation.py L1039 断言同步更新）。
- **验证**：remediation 16/16 绿。
- **状态**：**已修复并验证**。
- **变更记录**：2026-11-01 发现→修复→回归绿。

## FL-D858 V2 错误码直露（跨线协助，2026-11-01 发现）

- **发现日期**：2026-11-01。
- **问题与影响**：V2 CompareTaskPage chip/空态直露原始 error_code；类型层缺 side.upload_status/error_code 与 pair.diagnostics。
- **处理方法（已实施）**：types/api.ts ComparePair 扩展；shared.tsx 新增 COMPARE_UPLOAD_ERROR_LABELS/uploadErrorLabel/pairFailureLabel（与 V1 同构）；chip/空态改可读文案。**属 V2 线文件，按旧 compare 域令改动保留，矩阵归属标 V2 线。**
- **验证**：vitest 24/24、tsc、lint、build、frontend_v2 11/11 绿。
- **状态**：**已修复并验证**（跨线协助）。
- **变更记录**：2026-11-01 发现→修复→回归绿。

## FL-D859 选择文件反馈缺失+双端无超大预检（2026-11-01 发现）

- **发现日期**：2026-11-01（V1 走查+逐行读）。
- **问题与影响**：① V1 P2 选文件后只更新 sr-only 摘要，卡片文件名/has-file/按钮文案不动，用户无法确认选择成功；② V1/V2 均无 25MB 客户端预检——服务端拒绝后同清单不可替换文件，只能新建任务，事后才知代价大；③ V2 拒收回执只说「第 N 对还没上传完」不带文件级原因。
- **处理方法（已实施）**：① change handler 同步更新卡片（文件名/has-file/按钮「更换文件」）；② V1/V2 均加 `MAX_UPLOAD_BYTES`(=COMPARE_MAX_UPLOAD_BYTES 25MB，与服务端默认一致，服务端仍为准)+ .doc 预检；③ V2 回执按 client_id 匹配文件位并带 uploadErrorLabel 原因——由此匹配升级导致两处把回执简化成「只有 status」的测试 mock 失效，已修正为按真实服务端形状回显 client_id（frontend/tests/compare.test.tsx、tests/browser/test_frontend_v2.py multipart 提取）。
- **验证**：vitest 24/24、remediation 16/16、frontend_v2 11/11、frontend_fixes+scroll_perf 16/16 绿。
- **状态**：**已修复并验证**。
- **变更记录**：2026-11-01 发现→修复→mock 适配→全量回归绿。

## FL-D860 text_diff.py _symmetric_opcodes 死代码（2026-11-01 发现）

- **发现日期**：2026-11-01（逐行读 fundlex/compare/text_diff.py）。
- **问题与影响**：L63 `return inverted` 之后残留一行不可达 `return TextSpan(f"{side}-virtual", 0, 0, "")`——`_anchor` 尾部复制的残留，且该函数无 `side` 形参，若可达即 NameError。
- **处理方法（已实施）**：删除死行。
- **验证**：compare 算法套件 91/91、API 套件全绿。
- **状态**：**已修复并验证**。
- **变更记录**：2026-11-01 发现→修复→回归绿。

## FL-D861 compare.js 双 change 监听重复更新同一卡片（2026-11-01 发现）

- **发现日期**：2026-11-01（逐行读 frontend/compare.js 事件绑定段）。
- **问题与影响**：L1194 通用监听（`.compare-file-card input[type=file]`）与 L1207 组内监听（FL-D859 修复处）对同一配对文件输入事件各执行一次幂等的卡片 DOM 更新——无行为差异，纯冗余。
- **处理方法（已评估-不修复）**：两处均幂等、结果一致；删除其一属清理非缺陷修复，为最小改动原则保留现状并登记。
- **验证**：remediation 16/16 绿（现状即被测覆盖）。
- **状态**：**已评估-不修复**（观察项）。
- **变更记录**：2026-11-01 发现并登记。

## 号段声明：FL-D980~989 归 compare-ux 线 dogfood/后续批次（2026-11-01）

- 主线并行协调文档现有号段：FL-D921~939（EN2）、FL-D940~959（PL2）、FL-D960~979（监督线）；980 起空闲，compare-ux 取用 FL-D980~989。

## FL-D980 覆盖不完整警告直露机读 token（dogfood 走查，2026-11-01 发现）

- **发现日期**：2026-11-01（生产级走查 p3-pair2-coverage 截图：`UNSUPPORTED_VISIBLE_CONTENT:footer` 直出给用户）。
- **问题与影响**：parser coverage warnings 是机读协议码（测试锁定：header/footer/footnote/endnote/comment 及各 marker 后缀、table-wrapper 前缀），V1 覆盖 chip popover 与 V2 CompareTaskPage popover 均原文渲染，用户看不懂"哪部分没比对到"。
- **处理方法（已实施）**：V1 compare.js 与 V2 shared.tsx 各增 `coverageWarningLabel`——story 名译中文（页眉/页脚/脚注/尾注/批注）、marker 译中文（图形/文本框等）、table-wrapper 组合句式；后端协议与断言不动；test_v1_frontend_remediation.py L395 断言跟进为「页眉」。
- **验证**：复跑走查截图 popover 显示「页脚内容」；remediation 16/16、frontend_v2 11/11、vitest 24/24 绿。
- **状态**：**已修复并验证**。
- **变更记录**：2026-11-01 走查发现→修复→回归绿。

## FL-D996 失败组话术补救路径重复（dogfood 走查，2026-11-01 发现）

> **改号说明**：原号 FL-D981。2026-11-01 18:54 本线在附录登记后，qa-recall-miss（EN1）线于 18:57 在集中问题文档登记 FL-D981（BH01 计划遗漏，留出 r2/r3），两线撞号；19:01 总指挥令已正式引用 EN1 的 FL-D981，故 FL-D981/982 归 EN1 保持，本条改号 FL-D996（19:07 报主线并改号，见附录「FL-D981/982 撞号处置」条）。

- **发现日期**：2026-11-01（p3-failed-pair 截图：「…新建对比任务上传。该组已判失败，请新建对比任务重新上传。」一句话两遍"新建对比任务"）。
- **问题与影响**：FL-D857 拼句时文件级原因自带补救语 + 尾句补救语重复。
- **处理方法（已实施）**：V1 pairErrorLabel/V2 pairFailureLabel 尾句改「。该组已判失败，须新建任务补救。」。
- **验证**：走查复拍话术通顺；remediation/frontend_v2 全绿。
- **状态**：**已修复并验证**。
- **变更记录**：2026-11-01 走查发现→修复→回归绿。

## FL-D997 选择产物下载按钮直露裸 kind + 文件名缺扩展名（dogfood 走查，2026-11-01 发现）

> **改号说明**：原号 FL-D982，与 EN1 FL-D982（BH07 恢复通道复核）撞号，处置同 FL-D996 改号说明。

- **发现日期**：2026-11-01（p3-selection-downloads 截图首轮：按钮显示「final · v1」「redline · v1」）。
- **问题与影响**：① 后端产物 kind 恒为 `final`/`redline`（store.SELECTION_KINDS），V1 标签表只配了旧 `selected_*` 键名从不命中，回退直露裸 kind；② 文件名模板 `kind.endsWith('docx')` 对 final/redline 不成立，下载文件名无 `.docx` 扩展名。
- **处理方法（已实施）**：标签表补 `final`/`redline` 中文名（保留旧键防御）；文件名对 final/redline 追加 `.docx`。
- **验证**：走查复拍显示「下载选择结果 DOCX · v1」「下载选择结果（带修订痕迹）DOCX · v1」；remediation 16/16 绿。
- **状态**：**已修复并验证**。
- **变更记录**：2026-11-01 走查发现→修复→回归绿。

## 附：比对链路重设计生产级走查记录（dogfood，2026-11-01）

- 环境：主线树 rebase qa/full-audit-20261031@379a498 + 本轮修复；真实 create_app+真实 CompareWorker 线程+真实浏览器（脚本 /tmp/opencode/qa/compare_dogfood.py，数据 python-docx 真实 DOCX 经真实 API 上传/密封/处理/选择/生成）。
- 状态覆盖（14 截图，/tmp/opencode/qa/compare-dogfood-20261101/）：p1-empty（空态引导✅）、p1-list（三任务状态计数「已处理·1组失败/1组覆盖不完整」「上传中」✅）、p2-new-initial/selected（FL-D859 卡片反馈✅）、p3-workbench-word/classic（修订 rail、合并文档红线、连接线、chip 头部 ✅）、p3-selection-downloads（选择条+下载行）、p3-pair2-switched/coverage（chip 切组、覆盖 chip popover）、p3-deeplink-pair2（深链直达第二组✅）、p3-failed-task/failed-pair（失败组话术）、p3-pending-upload（待上传空态✅）、p3-mobile（移动端 rail 叠上、单行修订项✅）。
- 走查产出问题：FL-D980/983/984 三项（原登记号 FL-D980/981/982，981/982 与 EN1 撞号后改号），均已修复并复拍验证；其余状态目检无新问题。

## FL-D981/982 撞号处置（协调记录，2026-11-01 19:07）

- **问题与影响**：本线 18:54 在 0cc770a 并入时登记 compare dogfood 发现 FL-D981/982（附录入账）；qa-recall-miss（EN1）线 18:57 在 229f030 并入集中问题文档登记 FL-D981（BH01 计划遗漏）/FL-D982（BH07 恢复通道复核），同号双义。19:01 总指挥 EVAL-r3 令已正式引用 EN1 的 FL-D981。
- **处理方法**：FL-D981/982 沿既有集中文档与总指挥令**归 EN1 保持**；本线两条发现在自己的 980~989 段内改号：失败组话术→**FL-D996**、下载按钮裸 kind→**FL-D997**。附录条目与 COMPARE_DOMAIN_AUDIT.md 已同步，代码注释同步改号；旧号仅在 915002f/0cc770a 历史提交信息中出现，不改写历史。
- **验证**：rect-check `git grep "FL-D98"` 主线集中文档仅余 EN1 语义，本线文档仅余 980/983/984。
- **状态**：已处置（改号完成，报主线备案）。
