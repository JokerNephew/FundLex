# 合同比对并排对照 / 同步滚动复用接口说明（供 FL-D891 指引版本比对复用）

2026-11-01 · 合同比对前端专项线（FL-D840~842 同步滚动丝滑化 / splitter 重对齐 已入主线）。

## 实现位置

| 端 | 文件 | 关键符号 |
| --- | --- | --- |
| V1 | `frontend/compare.js` | `syncPaneScroll(source)`（统一入口）、`visiblePanels()`、`buildAlignmentModel()`/`mapAnchorIndex()`、`PaneVirtual`（`visibleBlock()`/`scrollToBlockIndex(index,fraction,settle)`/`scrollToBlockIndexEstimate(...)`）、`alignPanels()`、`bindCompareSplitter()`/`bindPanelSplitters()` |
| V2(React) | `frontend/src/pages/Compare/CompareTaskPage.tsx` | `syncScroll(source)`（useCallback）、`syncTargetsRef`/`syncFrameRef`/`syncReleaseRef`/`scrollLockRef`、`focusDiff`/`scrollToDiff` |

注意：V1 函数全部是 IIFE 闭包私有，**不可直接 import**；复用方式是拷贝模式或抽共享模块，勿新增对 compare.js 的跨页依赖。

## 可抽取的模块边界（按可复用粒度排序）

1. **滚动同步骨架**（最强复用点，与业务无关）
   - rAF 节流：每帧至多一次同步（`state.scrollFrame` / V2 `syncFrameRef`），等待帧期间只补绘连线。
   - 回声抑制：程序写 `scrollTop` 的目标 pane 进入 `syncTargets:Set`，其回声 scroll 事件直接早退；160~220ms 无事件后清空（`syncRelease`/`syncReleaseRef`）。写 listener 必须原生绑定 `{passive:true}`（React `onScroll` 永不 passive，会让合成器等主线程）。
   - 用户手势夺权：目标 pane 的 `wheel/pointerdown/touchstart`（passive）立刻清除抑制集，用户随时可接管某栏。
   - 程序聚焦护栏：`focusDiff` 期间置 `focusScrolling`/`scrollLockRef`，防聚焦触发的滚动回灌同步循环。
2. **对齐模型**（V1 独有，双栏长度不均时需要）：`buildAlignmentModel()` 用 `view.alignment`（left/right block_id 组）或 diffs 的 `block_id` 锚点建「块序号对应表」+ 相邻锚点线性插值（`mapAnchorIndex`）；merged 栏经 `rightToMerged/mergedToRight` 传递。回落链：对齐模型 → 块数比例 → 滚动条比例。
3. **重对齐时机**：布局变化不在拖拽中重算。`bindPanelSplitters()` 拖拽中只让浏览器自身 reflow + 连线重绘；`pointerup`（约 200ms settle）才 `refreshVirtualLayouts()`+`alignPanels()`。resize / 视图模式切换同理（对齐放 settle，不放每帧）。
4. **虚拟滚动接口**（仅长文档需要）：`_virtualDoc` 暴露 `visibleBlock()`（当前视口首块序号+块内偏移 fraction）与 `scrollToBlockIndex(index,fraction)`。150ms settle 重校验时，目标栏已在正确块（块序号一致且 |Δfraction|<0.25）**跳过** force-scroll——这是防抖动主修复（FL-D840），重实现勿漏。

## 接入方式（指引版本比对）

- **最短路径（推荐先按此做）**：指引原文/新版本并排若为整段 HTML 直渲、长度相近，直接搬 V2 `syncScroll`（~60 行，useCallback+4 个 ref，滚动条比例同步）。含 rAF 节流、回声抑制、手势夺权，无外部依赖。
- **需要块级对齐时**（如原文与生成新版长度差异大）：搬 V1 第 2/3 项——后端 payload 需提供 diff 锚点的 `block_id`（合同比对契约现成：`view.alignment` 或 `diffs[].left/right.block_id`），前端按 `buildAlignmentModel` 模式建映射；`view.alignment` 缺失时回落比例同步，可增量接入。
- 长文档（数百段）才需要 PaneVirtual 级虚拟化；指引版本比对量小可先用整渲 + 比例/块号同步。

## 注意事项（踩过的坑，逐项来自实测/走查）

1. 无回声抑制必现双栏乒乓/抖动；抑制释放用「无事件后定时清空」，不要用单帧释放（惯性滚动回声跨多帧）。
2. 程序聚焦 pane 必须 `focus({preventScroll:true})`，否则主滚动容器被甩走、页面顶部内容丢失（FL-D843 走查发现，已修复于 V1）。
3. 移动端（≤760px）只有单栏可见：同步早退，勿同步隐藏栏（`visiblePanels` 按 `offsetParent+clientHeight` 过滤）。
4. splitter 拖拽中做重测必卡顿（FL-D840 根因之一）：重测只放 pointerup/settle。
5. 测试参照：性能门禁 `tests/browser/test_compare_scroll_perf.py`（滚动流畅性 + 块级对齐断言），可直接仿写指引版比对同构门禁；对齐正确性断言模式见其 mock scenario。
6. 连线覆盖层（`#compare-lines`）为合同比对特有（diff 锚点连线），指引比对若无锚点可省略，仅保留滚动同步。
