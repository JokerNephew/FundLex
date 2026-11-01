# FL-D991 下拉框组件替换·完工报告（2026-11-01，qa-frontend-v2 树）

## 0. 用户原话 → 逐条断言表（S1 口径）

| # | 用户原话/工单要求 | 断言 | 结论 | 证据 |
| --- | --- | --- | --- | --- |
| U1 | 「下拉框的风格依旧很丑」 | V2 域 16 处下拉无一由原生 `<select>` 渲染，视觉统一为共享 Listbox | ✅ | ①同类清零命令输出：`grep -rn "<Select\|<select" frontend/src --include=*.tsx` → **0**；`grep -rn "ui-select\|control-select" frontend/src/styles frontend/src/components` → **0**；`<Listbox` 实例 → **16** ②对照截图见 §2 |
| U2 | 「你找找网上有没有别的组件能用的」 | 实际联网调研 React 生态候选（npm registry 元数据含 license 实据）并选型落地 | ✅ | §1 选型备案；`frontend/package.json` 含 `@headlessui/react ^2.2.10` |
| T1 | 键盘导航 | Space 打开/↑↓ 导航/Enter 选取/Esc 关闭全链路通过 | ✅ | vitest `tests/listbox.test.tsx`（8+3 项）；截图 `post-tasks-keyboard-focus.png`（方向键焦点项高亮） |
| T2 | 屏幕阅读器语义 | role/aria-haspopup/aria-expanded/aria-selected/label 命名链路 + axe 零违规 | ✅ | vitest 35/35（语义 3 项：aria 矩阵、label 包裹命名=「状态」（与原生 select 语义等同）、axe.run 零违规） |
| T3 | 移动端视口截图 | 390px 视口渲染不破、面板可开合 | ✅ | `pre-tasks-mobile.png` vs `post-tasks-mobile.png` + `post-tasks-mobile-open.png` |
| T4 | 替换前后对照截图 | 同机/同路径/同视口 pre(c03af74 构建) vs post 对照 | ✅ | §2 截图清单 |
| W1 | V1 不碰，集成由主线另行安排 | diff 不含 `frontend/*.js|html|css`（V1 壳）任何改动 | ✅ | commit `c77d384` 16 文件全部在 `frontend/src|tests` 与依赖清单；V1 集成说明移交文档 §V1 |
| W2 | 组件 API 文档 | 已产出并含 V1 集成说明 | ✅ | `docs/frontend/LISTBOX_COMPONENT_API_20261101.md` |
| W3 | S1 同类清零 | 16/16 替换+旧封装/死样式删除 | ✅ | U1 同组命令输出；旧 `Select.tsx` 已删除 |

## 1. 选型备案（联网核实，一句话+三维度）

**选型：@headlessui/react@2.2.10 的 Listbox**——用它因为「体积可接受（gzip +33.4 kB 换全站统一）、维护度有 Tailwind Labs 长期背书且 WAI-ARIA 行为开箱、零样式包袱使暗色/令牌适配零冲突」。

npm registry 实据（2026-11-01 拉取；三家 license 全 MIT，兼容）：

| 候选 | 版本（查实） | license | 直接依赖 | 维护信号 | 结论 |
| --- | --- | --- | --- | --- | --- |
| @headlessui/react | 2.2.10 | MIT | 5 个 | tailwindlabs/headlessui 官方仓库，v2 线持续发布 | **采用** |
| @radix-ui/react-select | 2.4.1 | MIT | ~20 个（popper/portal/scroll-lock 族） | radix-ui/primitives 活跃（2026-10-14 更新） | 依赖链过重，收益相同，否决 |
| @floating-ui/react | 0.27.20 | MIT | 仅定位引擎 | floating-ui 活跃 | 交互语义需自研=重写 Headless UI，否决 |
| antd Select | 6.6.8 | MIT | 全量 antd | 已在 node_modules 但 src 零引用（历史死依赖） | 视觉语言与令牌体系冲突，否决 |

- **体积**：index chunk gzip 134.68 kB（c03af74）→ 168.08 kB（实现后），+33.4 kB，自研/换皮成本对比下接受。
- **维护度**：Headless UI 由 Tailwind Labs 维护（react-aria/floating-ui/tanstack-virtual 组合为业界标准底座），MIT；比自研少一层自维护键盘/焦点/typeahead 语义。
- **暗色主题/样式适配**：零自带样式、className/数据属性全自控，按钮并入 `--ctl-*` 控件令牌矩阵、面板走 `--surface`/`--border-strong`/`--shadow-overlay` 令牌——后续暗色主题只需令牌换值，组件零改动（本工单未引入任何硬编码品牌色之外的视觉值；箭头/勾选用品牌令牌色）。
- package.json 此前遗留改动即本工单选型安装的 `@headlessui/react ^2.2.10`（已随 c77d384 提交），本报告一并交代。

## 2. 截图证据（真实 Chromium，T 本机临时 dev 服务，`FUNDLEX_AUTH_MODE=dev`）

拍摄方法：`c03af74`（替换前）独立 worktree + 同 node_modules 构建 pre-dist，与当前构建在同一 uvicorn 服务下分别拍摄；视口桌面 1440×900 / 移动 390×844，同路径 `/tasks`、`/models`。

| 文件（`docs/frontend/evidence/listbox-20261101/`） | 内容 |
| --- | --- |
| `pre-tasks-desktop.png` / `post-tasks-desktop.png` | 任务页筛选条前后对照：原生样式箭头参差 → 统一按钮语言（圆角/边框/▾ 一致） |
| `pre-models-desktop.png` / `post-models-desktop.png` | 模型配置「使用方式」（工单点名原生 select 代表）前后对照 |
| `post-tasks-open-panel.png` | 面板打开：贴底展开、与按钮等宽、品牌色选中✓、chevron 翻转、投影 |
| `post-tasks-keyboard-focus.png` | 方向键导航后焦点项高亮（键盘可达视觉证据） |
| `pre-tasks-mobile.png` / `post-tasks-mobile.png` / `post-tasks-mobile-open.png` | 390px 移动端前后对照+面板打开 |

## 3. 质量双保险

- **A 自拍截图自检**：即本报告 §0/§2（真实服务自拍、回读复核通过）。
- **B 质检子agent**：⚠️ 如实申报——当前会话工具集无 `subagent`/agent 派生工具（可用：shell/grep/read/write/edit/webfetch/websearch/skill/execute），无法自建双盲质检子agent。已用最强替代：①四闸机器证据全绿；②截图回读人检；③浏览器 3 用例真实回归。**申请主线补派独立质检**（材料：`git diff c03af74..HEAD` + 本报告 + 截图目录）。

## 4. 命令输出账本与四闸

- `npx tsc --noEmit` → 0 错；`npx vitest run` → 7 文件 35/35 绿；`npx vite build` → ✓（index 532.85 kB / gzip 168.08 kB）；浏览器（Playwright 真实 Chromium）：`test_model_roles_and_confirmed_connection_test`、`test_new_task_manifest_search_filter_pagination_and_compare_entry`、`test_compare_result_view_supports_pair_navigation_and_mobile_switching` 3/3 PASS（锚点 2 处随工单有意升级：select_option→button+option 点击、页级定位）。
- 模型调用账本：本工单零真实模型调用（纯前端），无费用。
- Commit 链：`c77d384`（实现+替换+测试+浏览器锚点）→ `eaed57e`（API 文档+集中册）→ `825cd36`（语义测试补强）→ 本报告 commit（证据+文档收口）。
