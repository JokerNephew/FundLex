# 比对滚动联动 + 分栏 Splitter 复用接口说明（COMPARE_SCROLL_REUSE_NOTES）

> 面向指引版本比对（FL-D891，前端主线施工）。比对工作台（frontend/compare.js）的滚动丝滑体系由四层组成：**分栏 splitter（app.js 全局函数）→ 虚拟化容器（VirtualDocument）→ 块索引对齐模型（alignment model）→ rAF 联动滚动 + 连接线**。FL-D891 复用时按本单接线，不要重造；也不要整文件拷贝 compare.js（选择条/任务轮询/上传等域逻辑与指引比对无关）。
> 基线：qa/full-audit-20261031 @ 379a498。所有行号以该版为准，漂移时以函数名检索。
> 注意：V1 函数全部是 IIFE 闭包私有，**不可直接 import**；复用方式是拷贝模式或抽共享模块，勿新增对 compare.js 的跨页依赖。

## 0. 接入路径速选（先读这段）

- **最短路径（量小先按此做）**：指引原文/新版本并排若为整段 HTML 直渲、长度相近，直接搬 **V2 React `syncScroll`**（`frontend/src/pages/Compare/CompareTaskPage.tsx`，~60 行 useCallback+`syncTargetsRef`/`syncFrameRef`/`syncReleaseRef`/`scrollLockRef` 四个 ref，滚动条比例同步）。含 rAF 节流、回声抑制、手势夺权，无外部依赖。
- **需要块级对齐时**（原文与生成新版长度差异大）：搬 §3 对齐模型——后端 payload 需提供 diff 锚点 `block_id`（合同比对契约现成：`view.alignment` 或 `diffs[].left/right.block_id`），缺失时回落比例同步，可增量接入。
- **长文档（数百段）才需要** §2 VirtualDocument 级虚拟化；指引版本比对量小可先用整渲。
- 连接线（§5）为合同比对特有（diff 锚点连线）；指引比对若无锚点可省略，仅保留滚动同步。

---

## 1. 分栏 Splitter：`window.FundLexColumnSplitter(handle, container, target, options)`

定义：`frontend/app.js` `bindColumnSplitter`（注册于 `window.FundLexColumnSplitter`，早于各视图脚本加载）。usage 参照 `frontend/compare.js` `bindPanelSplitters()`。

**参数**

| 参数 | 类型 | 说明 |
|------|------|------|
| `handle` | Element | 拖拽句柄（建议 `role="separator"` + `tabindex="0"`，函数内部只负责 aria-valuenow/min/max/text 与键盘事件，role 由你标） |
| `container` | Element | 布局容器，其 CSS 变量被改写（grid-template-columns 引用该变量） |
| `target` | Element \| () => Element | 被调宽的面板；传函数以应对面板重渲染 |
| `options` | object | 见下 |

**options**（默认值见 app.js 定义）

| 键 | 默认 | 说明 |
|----|------|------|
| `key` | `''` | localStorage 持久键；空串不持久化 |
| `variable` | `--column-width` | 写 px 到 container 的 CSS 变量名 |
| `min` / `max` / `minOther` | 220/680/420 | 宽度边界；实际上限 = container.clientWidth − minOther |
| `fallback` | 320 | 初值/双击复位值 |
| `side` | `'right'` | 或函数返回 `'left'/'right'`，决定拖拽方向（视图切换可镜像，compare 用它切 classic 左右） |
| `disabled` | `() => false` | 移动端返回 true 即禁用拖拽与键盘 |
| `onChange(width)` | null | 每帧宽变回调（**保持轻量**，见 §4 性能契约） |
| `onEnd(width)` | 无默认 | pointerup 后回调一次——重几何工作（重测量/重对齐）只许放这里 |

**返回**：`{apply, width, dispose} | null`；窗口 resize 时全局注册表自动收尸失连句柄（A9-F04）。键盘：←/→（shift 加速）、Home/End、Enter/Space 复位；dblclick 复位 fallback。

**CSS**：句柄样式抄 `.compare-column-splitter` / `.review-splitter`（app.css L769~806，含 ::before 指示条、is-dragging/focus-visible 态），容器侧 grid 列引用你的变量：`grid-template-columns: minmax(0,1fr) 6px var(--guide-diff-rail-width, 300px)`。

---

## 2. 虚拟化容器：`class VirtualDocument`（frontend/compare.js）

**构造**：`new VirtualDocument(container, document, options)`

- `document` — 用 `parseVirtualDocument(html)` 生成：`{style, blocks: [{html, blockId, blockIds[], diffIds[], textLength, kind}]}`。块级 id 是联动锚定的唯一依据，**后端 HTML 必须在块/差异标记上带 `data-block-id` / `data-diff-id`**（指引比对同此要求——render 层职责）。
- `options`：

| 键 | 默认 | 说明 |
|----|------|------|
| `chunkSize` | 20 | 每 chunk 块数；`virtualize()` 封装里 ≤400 块自动整块挂载（中小文档免测量抖动），大文档保持 20 窗口首屏快 |
| `overscan` | 2 | 视口上下多挂 chunk 数 |
| `charsPerLine` | 46 | 高度估计精度（源文档窄栏用 30/40，主文档 48） |
| `merged` | false | 追加 `compare-merged-document` 类 |
| `collectMarks` | false | 测量同帧收集 `[data-diff-id]` 几何到 `.marks`（连接线用，见 §5） |
| `onChange` | null | refresh 完成回调（compare 里重收集 marks+补活动态） |

**方法与属性**：`refresh(force, forcedRange?)`、`destroy()`、`resetMeasurements()`、`visibleBlock() → {index, fraction}|null`、`scrollToBlock(blockId)`、`scrollToBlockIndex(index, fraction?, settle?)`、`scrollToBlockIndexEstimate(index, fraction?)`（settles 前的估计跳）、`.blockIndex`（id→块序号）、`.marks`（collectMarks 时）、`.blocks`。

**内建性能契约（复用即得，勿绕过）**：
- refresh 快路径：范围未变且无脏 chunk → 直接 return（settles 风暴的命门，FL-D840）。
- 换 chunk 前先 `wrapper.style.minHeight` 顶住滚动范围，防浏览器 clamp。
- 锚点保持：有可见块保可见块像素位；否则保 chunk 锚点；`anchorLockUntil` 防程序滚动后被误回拉。
- **CSS 必备**：容器 `overflow-anchor:none`（虚拟块替换禁用浏览器自动重锚）；`.compare-virtual-chunk{display:flow-root}`。
- `zoom` 缩放面板（如源文档 .72/.8）自动经 `getComputedStyle(wrapper).zoom` 修正 spacer 高度，不要在 JS 里再除。

---

## 3. 对齐模型：`buildAlignmentModel` / `mapAnchorIndex`（compare.js）

**输入数据约定**（FL-D891 后端 view 负载需提供）：
- `view.alignment: [{left: [blockId...], right: [blockId...]}]`（对齐组，**首选**）；缺省时退化用 `view.diffs[*].left/right(.block_id)` 或 `*_anchor`/`*_spans[0]` 反推锚点。
- 各文档 `blocks` 经 parseVirtualDocument 得 `blockIndex`（blockId + 内部 blockIds + diffIds 多键映射）。

**产物**：
- `model.anchors` — 单调递增的左/右块序号锚点列（含首 0/0、尾 last/last；构造时清理逆序冲突）。
- `mapAnchorIndex(index, from, to, model)` — 锚点间线性插值（fraction 由调用方另行保留）。
- compare 另有 merged 文档桥（`rightToMerged/mergedToRight/leftToMerged/mergedToLeft`）：只有一个合并视图+两个源视图时需要；**指引比对若只有左右两栏可删掉整条 merged 映射**。

---

## 4. 联动滚动：`syncPaneScroll(source)` 模式（compare.js）

**状态机与护栏**（四个全局件，少一个都会打架）：
1. `state.syncTargets: Set` — 程序写入的目标栏集合，目标的 scroll 事件回环到此被忽略（防回环）。
2. `state.scrollFrame` — rAF 闸刀：同一手势只跑一次。
3. `state.focusScrolling` — diff 跳转期间联动让位。
4. 三个计时器：`syncSettle`（150ms 校验性二次对齐）、`syncRelease`（220ms 清 syncTargets）、`lineSettle`（90ms 连接线重算）。

**流程**：rAF 内 `source.visibleBlock()` → alignment 模型映射出各目标块序号 → `scrollToBlockIndexEstimate`（先估计跳，不等测量）→ 150ms settle 再 `scrollToBlockIndex` **校验后再跳**（目标已在位±0.25 fraction 就跳过，防每 150ms 强刷）→ 220ms 后释放。

**用户抢占**：`wheel/pointerdown/touchstart` 各栏注册 `takeControl`（清 settle+syncTargets）——用户接管任何一栏即断开联动，不滚了。

**性能契约（FL-D840/841，复用者必须遵守）**：
- splitter 拖拽中 onChange 只许重画连接线（轻量）；重测量/重对齐全部放 onEnd。键盘微调防抖 200ms 合并重活。
- 宽度变化后不要按滚动条比例回对——块索引模型重对（scheduleAlign 120ms 防抖）。
- `alignPanels()`：主动发起，固定选 canonical 源栏（compare：word 视图=merged，classic=左栏）作为 source 调 syncPaneScroll。
- 移动端（≤760px 单栏）drawLines 直通不走模型。

---

## 5. 连接线：`drawLines`（compare.js，classic 双栏视图专属）

- SVG `#compare-lines` 绝对铺在栏容器上（`pointer-events:none`），viewBox=容器 rect；路径为左右 mark 中点三次贝塞尔。
- mark 几何来自 `collectMarks` 在测量同帧收集（**不要**再为画线做一次 240-rect 查询）。
- 视口裁剪：非活动 diff 且两侧都超出视口 ±80px 跳过；总量 240 条封顶；活动的那条永远画（`.active` 类换主色）。
- 滚动中淡出：容器挂 `.is-sync-scrolling`（opacity 0，CSS transition），90ms settle 后重算——滚动期间**不**逐帧重建 path。

---

## 6. FL-D891 接线清单（指引版本比对专用）

1. **后端 view 负载**：版本 diff HTML 块带 `data-block-id`，差异行内标记带 `data-diff-id`；负载带 `alignment` 组（或至少 diff 级 left/right block_id 锚点）。guide diff 已有 `guide-diff-pane`/merged 三态（app.js L1279），换数据不换协议。
2. **最小骨架**：parseVirtualDocument ×2（左右）→ virtualize ×2 → buildAlignmentModel（删 merged 映射）→ syncPaneScroll(scroll 源=当前指针所在栏) → splitter ×1（rail 宽）可选。
3. **抄即可**：`parseVirtualDocument`、`VirtualDocument`、`virtualize`、`refreshVirtualLayouts`、`mapAnchorIndex`、`syncPaneScroll` 框架 + §5 drawLines（如需指示线）。**建议中期把这一组抽出 compare.js 为静态模块**（如 `frontend/panesync.js`）两条线共引，compare.js 保留域逻辑——抽出时 compare 侧回归门禁：tests/browser/test_compare_scroll_perf.py + test_v1_frontend_remediation.py 16 测必须全绿。
4. **不要抄**：selection 决策条/上传/任务轮询/chip 切换路由（compare 域）；`scalePaneDimensions`（Word pt 缩放，指引 HTML 无内联 pt）可删。
5. **验收自查**（与 compare 同门禁口径）：120Hz 连续滚动无掉帧感；splitter 拖拽无顿（对照 test_workbench.py::test_review_list_splitter_drag 同型断言）；宽度改变后两栏段落对应不丢；diff 跳转后联动 1 次 settle 内归位。性能门禁可直接仿写 `tests/browser/test_compare_scroll_perf.py`（滚动流畅性+块级对齐断言，mock scenario 可作对齐正确性断言模板）。

## 7. 踩过的坑（逐项来自实测/走查，重实现勿漏）

1. 无回声抑制必现双栏乒乓/抖动；抑制释放用「无事件后定时清空」，不要用单帧释放（惯性滚动回声跨多帧）。写 scroll listener 必须原生绑定 `{passive:true}`——React `onScroll` 永不 passive，会让合成器等主线程。
2. 程序聚焦 pane 必须 `focus({preventScroll:true})`，否则主滚动容器被甩走、页面顶部内容丢失（FL-D843 走查发现，已修复于 V1；B 重设计 region 化后聚焦在 viewer 本身）。
3. 移动端（≤760px）只有单栏可见：同步早退，勿同步隐藏栏（`visiblePanels` 按 `offsetParent+clientHeight` 过滤）。
4. splitter 拖拽中做重测必卡顿（FL-D840 根因之一）：重测只放 pointerup/settle。
5. 滚动同步 settle 重校验时，目标栏已在正确块（块序号一致且 |Δfraction|<0.25）**跳过** force-scroll——这是 FL-D840 防抖动主修复。
6. 双实现基准：V1（compare.js 闭包，§1~§5 全部件）与 V2（CompareTaskPage hooks 版，仅滚动同步骨架）行为对齐；改任一侧契约时两侧都要过各自浏览器门禁。

—— compare-ux 线，2026-11-01（协同单欠账交付；问题反馈走 docs/DETAIL_APPEND_COMPARE_UX.md 追加）
