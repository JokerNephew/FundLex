# 统一下拉组件 Listbox API（FL-D991，2026-11-01）

> 工单：用户原话「下拉框的风格依旧很丑，你找找网上有没有别的组件能用的」。V2 域 16 处原生 `<select>`/旧 `<Select>` 封装已全量替换；V1 页面集成本线不碰（FE 负责），本文即交接文档。

## 选型结论（一句话备案版）

**@headlessui/react@2.2.10 Listbox**：零样式包袱、WAI-ARIA 完整实现（键盘导航/焦点管理/aria 角色/typeahead 开箱）、className 全自控与 `--ctl-*` 令牌体系零冲突。

调研对比（npm registry 实据，2026-11-01 取数；websearch 集成当时无返回）：

| 方案 | 版本 | 依赖链 | 判定 |
| --- | --- | --- | --- |
| @headlessui/react | 2.2.10 | 5 个直接依赖 | **采用**：样式零侵入，可访问性开箱 |
| @radix-ui/react-select | 2.4.1 | ~20 个直接依赖（含 react-remove-scroll/popper/portal 族） | 依赖链过重，收益相同 |
| @floating-ui/react | 0.27.x | 仅定位引擎（交互语义需自研） | 自研=重写 Headless UI，不值得 |
| antd Select | 6.6.8 | 已在 node_modules 但 src 零引用（历史死依赖） | 视觉语言与令牌体系冲突，否决 |

体积代价：index chunk gzip 134.68 → 168.08 kB（+33.4 kB），换全站统一可达下拉，接受。

license 联网核实（2026-11-01，npm registry `npm view <pkg> version license time.modified repository.url`）：三家全 **MIT**，兼容；@radix-ui/react-select 2026-10-14 仍在更新但依赖链~20 过重结论不变。维护度：Headless UI 属 Tailwind Labs 长期维护线（react-aria+floating-ui+tanstack-virtual 标准底座）。暗色主题/样式适配：零自带样式、className/数据属性全自控，按钮并入 `--ctl-*` 矩阵、面板走 `--surface`/`--border-strong`/`--shadow-overlay` 令牌——暗色主题只需令牌换值，组件零改动。三维度完整论证与截图证据见 `FL_D991_COMPLETION_REPORT_20261101.md`。

## 组件

`frontend/src/components/ui/Listbox.tsx`（经 `components/ui` 桶导出；旧 `Select.tsx` 已删除）。

```tsx
<Listbox
  value={当前值}
  onChange={(value) => ...}      // 直传所选值（非事件对象），类型随 value 泛型推导（string | number）
  options={[{ value, label, disabled? }]}  // label 支持 ReactNode
  label="无障碍名称"               // 可选；被可见 <label> 文字包裹时可省略
  className="紧凑变体类"           // 可选，加到按钮上
  disabled={busy}                 // 可选
/>
```

行为约定：

- **类型**：`string | number` 泛型；数值型值原样回传（分页「每页条数」即 number 直传直收）。
- **无匹配兜底**：`value` 不在 options 时按钮展示首项（与原生 select 一致），不回显原始码。
- **表单安全**：按钮固定 `type="button"`，在 `<form>` 内开合/选取不会触发提交。
- **选项面板**：`anchor="bottom start"` 贴按钮下缘展开，Portal 到 body 末尾（z-index 60），面板 `min-width: var(--button-width)` 与按钮等宽，max-height 280px 滚动。
- **键盘**：Space/Enter/↓ 打开；↑/↓ 导航；Enter 选取；Esc 关闭；字符 typeahead（Headless UI 内建）。

## 样式契约（与 V1 复刻对齐的基准）

按钮复用控件令牌矩阵（`app.css` 状态矩阵已把 `.ui-listbox-button` 纳入 `input, textarea` 同组规则）：

| 类名 | 用途 | 关键令牌 |
| --- | --- | --- |
| `.ui-listbox-button` | 触发按钮 | `--ctl-border/height/radius/pad-*`、hover → `--ctl-border-hover`、`:focus-visible` → `--ctl-border-focus`+`--ctl-focus-ring`、`:disabled`/`[data-disabled]` → `--ctl-disabled-bg` |
| `.ui-listbox-value` | 按钮内当前值（省略号截断） | — |
| `.ui-listbox-chevron` | ▾ 指示符，`[data-open]` 时旋转 180° | `--dur-fast`/`--ease-standard` |
| `.ui-listbox-options` | 浮层面板 | `--surface`、`--border-strong`、`--radius-sm`、`--shadow-overlay`（tokens 新增）、z-index 60 |
| `.ui-listbox-option` | 选项行 | `[data-focus]` → `--surface-subtle`；`[data-selected]` → `--brand-dark` 加粗+`--brand` ✓；`[data-disabled]` → `--muted` |

Headless UI v2 数据属性（注意非旧版 active）：`data-focus`、`data-selected`、`data-disabled`、`data-open`、`data-closed`。

## 调用点（16 处，V2 全量）

Tasks/index.tsx 4（每页条数 number、状态、指引版本、排序）、TaskDetail/index.tsx 4（排序、处理状态、交付状态、上传状态）、Users/index.tsx 1（角色）、NewTask/index.tsx 1（文件筛）、Compare/shared.tsx 2（痕迹显示、差异筛选）、Guides/CompareCard.tsx 2（基准/对比版本）、Settings/ModelSettings.tsx 2（使用方式、供应商）。

## V1 集成说明（交 FE 线）

- V1（`frontend/app.js/compare.js` 原生 JS + `frontend/app.css`）不能直接引用 React 组件；FE 线如要对齐观感，推荐任选：①同版本 `@headlessui/react` 经 CDN + 在 V1 壳内挂微型 React 岛；②按上表「样式契约」用原生 button+ul 复刻同一套 `.ui-listbox*` CSS（令牌与数据属性语义照搬即可，CSS 无框架依赖）。
- 交互语义对齐点：键盘可达（Space/Enter/↓、↑↓、Esc、typeahead）、焦点环、disabled 态、面板等宽+贴底展开+z-index 60、选中 ✓。
- 测试侧锚点注意：替换后元素不再是 combobox/select，Playwright `select_option` 失效，应走 `get_by_role("button").click()` + `get_by_role("option", name=...).click()`（选项面板 Portal 到 body，用 page 级定位）。

## 验证（本工单四闸全绿）

- `tsc --noEmit` 0 错；vitest 7 文件 32 项全绿（新增 `tests/listbox.test.tsx` 8 项：渲染/鼠标选取/string·number 回传/键盘 Space·↓·Enter/Esc/禁用/表单不提交/无匹配兜底）；`vite build` ✓；浏览器 3 用例 PASS（模型配置「使用方式」、新建任务文件筛、对比查看器回归）——浏览器锚点两处随 FL-D991 有意升级（`select_option` → button+option 点击，先例见主线 3237af1/38997a5）。
