# 列表统一规范（form-ui，2026-11-01，项 4 / FL-D731）

> 用户二度返工点：「各列表风格不一致，看起来像是没改」。本规范是全仓唯一的列表/表格实现基准，V1（app.js/compare.js/guide_generation.js/workspace.js + app.css/compare.css/guide_generation.css）与 V2（frontend/src/**）同时执行。**不做视觉换肤大改，而是把现有两套前端的列表收敛到同一 token 与同一形态**，让任何两个页面并排时字体/行高/按钮/徽标一致。

## 一、列表 token（所有列表必须通过变量取这些值）

字号/间距/圆角沿用既有阶梯（text-2xs:11 徽章 / text-xs:12 表头注释 / text-sm:13 表格正文 / text-md:14 块级标题；spacing 4/8/12/16/24/32；radius 6/10/pill）。列表另增专用变量（V2 进 `src/styles/tokens.css`，V1 进 `app.css :root` 并同步别名）：

| Token | 值 | 用途 |
| --- | --- | --- |
| `--list-header-bg` | `var(--surface-subtle)` | 表头行背景 |
| `--list-header-color` | `var(--muted)` | 表头字色 |
| `--list-row-hover-bg` | `var(--surface-subtle)` | 行 hover |
| `--list-row-border` | `var(--border)` | 行分隔线 |
| `--list-cell-y` | `10px` | 单元格上下 padding |
| `--list-cell-x` | `12px` | 单元格左右 padding |
| `--list-title-weight` | `600` | 行内主标题/文件名 |
| `--list-meta-size` | `11px`（--text-2xs） | 行内次要说明 |

## 二、表格形态（所有列表页唯一实现）

1. **实现类**：V2 现有 `.data-table` 是唯一表格类（已 token 化，本次只做残点收敛）；V1 唯一的表格类定为 `.table`（`#task-rows #doc-rows #user-rows #guide-rows #i-list #import-rows #workspace-task-rows #compare-task-list #compare-pair-list` 及 guide_generation 的表格容器统一走它），compare.css / guide_generation.css 中任何覆盖表格字号/padding/行高的局部规则**一律删除或改为引用 token**，不再独立定义网格表格样式。
2. **表头**：`th` 12px、600、`--list-header-color`、背景 `--list-header-bg`、首/末单元格圆角沿用容器；**每个列表的表头少一行重复计数/解释**（计数放卡片副标题或分页行）。
3. **单元格**：13px、padding `--list-cell-y/--list-cell-x`、下边框 1px `--list-row-border`、hover 行背景 `--list-row-hover-bg`；行内主标题 `<strong>` 或 `.filename` 用 `--list-title-weight`；行内副说明 11px `var(--muted)`，**最多 1 行**。
4. **行内操作**（每个列表最多 2 个常用动作 + 其余进详情页）：
   - 主动作（查看/进入）：`.btn btn-sm btn-primary`（V1）/ `Button variant="primary"`（V2）。
   - 次动作（下载/复制/删除等）：`.btn-link`（V1，无边文字钮）/ `Button variant="quiet"`（V2）。**禁止在同一行混用 `.btn`（带框）与纯文本链接**。
   - 禁用态统一：`disabled` 属性 + 阶梯对比度（`--muted` 文字）、title 一句话原因。
5. **徽标**：语义徽标统一 pill、11px、soft 底+纯色字（success/warning/danger/muted 四系）；V2 `StatusBadge` 已如此，V1 `.badge`/`.pill` 对齐同一 padding/字号/圆角，**不得各页另写**。未知状态一律「未知状态」，不回显英文原值。
6. **空态/加载态**：空态文案一句话 + 渐进色块；禁止英文 placeholder、禁止裸「No data」。`aria-busy` 下表格主体半透明即可。
7. **分页**：统一「共 N 条 · 第 x/y 页」+ 上一页/下一页两个 `.btn btn-sm`，V1/V2 同文案同形态。
8. **非表格列表**（V1 compare pair 卡、guide_generation 候选条目、通知列表、V2 修订卡 `RevisionCard`/统计卡）：卡面统一 `.card card-pad` ≈ `.ui-card` 同 padding（16/20）、radius 10、border 1px `var(--border)`、shadow `var(--shadow)`；卡内列表行 13px + `--list-cell-y` 上下间距；卡内按钮遵守第 4 条。
9. **容器**：表格外层 `.table-wrap`/`.table-scroll`（横向滚动容器）统一圆角+border；不在表格上堆 box-shadow。

## 三、V1/V2 实施范围（worker 各自域）

### V1 worker（ivRkf1jH，编号 750-759）
- `app.css :root` 增第二节 `--list-*` 变量（值与 V2 一致）。
- `.table th/td/hover/空态/分页/徽标/row-action` 全部按第二节收敛；`app.css/compare.css/guide_generation.css` 中一切覆盖表格字号/padding/行高/表头背景的局部规则删除或改 token 引用（自查目标：三个 CSS 里 `td{padding:`/`th{padding:` 只出现一次且引用 token）。
- 22 处 `.btn` 定义收敛：`.btn` 基础+`.btn-sm`+`.btn-primary/.btn-danger/.btn-quiet/.btn-link` 六形态唯一规范，compare.css（19 处）与 guide_generation.css（2 处）只加文件级布局变体，不重定义形态。
- V1 各页面行操作按第 4 条执行：如任务列表「查看」保持 `.btn-link btn-sm`；文档行「查看」同形态；指引行「规则组/启用/解析/下载」收敛到主+次。
- 不改任何 id/data-action/文案锚点（浏览器测试 40+ 锚点照旧）。

### V2 worker（81FirpsQ，编号 760-769）
- `tokens.css` 增 `--list-*` 变量并在 `app.css` 把 `.data-table` 相关规则改为引用。
- 各页面 `<table>` 保持 `.data-table`；删除 TaskDetailIndex 与 Tasks 之间残留的排版差异；`RevisionCard`/统计卡/ComparePage 卡面遵守容器与按钮规范。
- 行内操作全站统一主/次形态：行内最多 1 个 primary + 次级用 quiet；`ViewButton` 之类自封控件不新建。
- 保留 vitest/浏览器锚点（按钮文案、「指引配置」等）。

## 四、验收（前端主线执行）

1. 并列比对截图（Playwright）：任务列表、文档行、指引列表/规则组、用户管理、对比任务列表在 V1 与 V2 同尺寸的表头/行高/按钮/徽标像素级一致（同一 token 值渲染结果）。
2. `rg "font-size: *[0-9.]*px"` 三 CSS + V2 app.css 中 11-30 阶梯外的值=0（徽章 11 例外已含阶梯）。
3. 行内按钮不出现带框 `.btn` 与文本链接混排；薇标字体/圆角两版一致。
4. 浏览器既有锚点用例全绿；无新增未映射英文 status。
EOF
