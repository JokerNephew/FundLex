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

## 附：工单 B（链路重设计）状态

- 方案已写 [docs/frontend/COMPARE_CHAIN_REDESIGN_20261101.md](frontend/COMPARE_CHAIN_REDESIGN_20261101.md)（现状信息分布、三禁令删除清单、P1/P2/P3 页面划分、布局规格、迁移兼容、FL-D843~848 拆解），按号令**报主线过目后动工**；A/B 合并排期建议：A 已完可先行合并，B 待主线批准方案后按 FL-D843→847 顺序施工。
