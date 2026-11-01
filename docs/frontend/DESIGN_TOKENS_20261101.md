# FundLex 设计令牌源（2026-11-01，第三轮）—— 全站唯一引用档案

> 本文档是动效/组件令牌的**定义源**；V1 `frontend/app.css :root` 与 V2 `frontend/src/styles/tokens.css` 为镜像实现，两端同名同值。新增/修改令牌必须先改本文档再改实现，禁止页面级散写（规划文档 DESIGN_CONVERGENCE_PLAN_20261101.md §二/§三为设计依据）。
> 色名映射：V1 `--accent*` ↔ V2 `--brand*`；V1 `--ink/--muted/--line*` 两端同名。

## 1. 字体

| 令牌 | 值 | 说明 |
| --- | --- | --- |
| `--font-ui` | `Inter,"PingFang SC","Microsoft YaHei UI","Noto Sans SC",system-ui,sans-serif` | 全站工作字体（消灭 V1 Segoe UI 系双轨，FL-D803） |

文书区（合同正文/比对文档）保持 Serif 族不变（`"Songti SC","Noto Serif SC",...`），不属工作字体。

## 2. 动效（唯一规格，克制微动效）

| 令牌 | 值 | 用途 |
| --- | --- | --- |
| `--dur-press` | `50ms` | 按钮按压位移 |
| `--dur-fast` | `120ms` | hover 底色/边框微反馈 |
| `--dur-med` | `200ms` | 常规状态过渡（边框/阴影/颜色/透明度）、toast/背板 |
| `--dur-slow` | `250ms` | 弹层/抽屉开合（进） |
| `--ease-standard` | `cubic-bezier(.2,.6,.25,1)` | **全站唯一缓动**；无限循环动画（spinner/pulse）允许 `linear`/`ease-in-out` |

- **允许动画属性集**：`background-color, border-color, color, box-shadow, opacity, transform`。**禁止 width/height 盒尺寸过渡**（布局抖动）。
- 弹层：背板 fade 200ms；面板开合 250ms 进 / 150ms 出。页面/视图进场：opacity+translateY(4px) 200ms。
- `@media (prefers-reduced-motion: reduce)`：关闭全部动画与过渡。

## 3. 表单控件（input/select/textarea 全状态矩阵）

| 令牌 | 值 | 状态 |
| --- | --- | --- |
| `--ctl-border` | `var(--line-strong)` (#cfd5db) | rest |
| `--ctl-border-hover` | `#aeb7c0` | hover |
| `--ctl-border-focus` | `var(--accent)` / `var(--brand)` | focus |
| `--ctl-focus-ring` | `0 0 0 3px rgba(181,71,30,.14)` | focus 环 |
| `--ctl-radius` | `6px` | 统一（消灭 V2 form-stack 8px 分裂） |
| `--ctl-height` | `36px` | 输入与下拉同高 |
| `--ctl-pad-y` / `--ctl-pad-x` | `6px` / `10px` | |
| `--ctl-placeholder` | `#98a1a9` | 占位文本色 |
| `--ctl-disabled-bg` | `#f5f6f8` | 禁用 |
| `--ctl-chevron` | 唯一内联 SVG（12px，`stroke:#68717c`） | select 自定义箭头，`appearance:none; padding-right:30px` |
| 选项（原生 option） | `min-height:28px`；`option:checked` 背景 `var(--accent-soft)` | 可样式化部分 |
| 长选项滚动容器 | `max-height:260px; overflow:auto; border-radius:6px` | |

## 4. 徽标（badge 唯一规格）

| 令牌 | 值 |
| --- | --- |
| `--badge-size` | `11px` |
| `--badge-weight` | `650` |
| `--badge-pad` | `3px 9px` |
| `--badge-radius` | `999px`（pill，无边框） |

## 5. 列表（唯一规格，追责项；逐项断言基准）

| 令牌 | 值 | 说明 |
| --- | --- | --- |
| 表体/表头字号 | `13px` / `12px 600` | |
| cell padding | `10px 12px`（`--list-cell-y/x`，既有） | |
| hover 行 | `var(--surface-soft)` (#f7f9fa) | 消灭 gg `#fdfbf9` |
| 主键文本 | `fw600 var(--ink)`，溢出截断 | V2 品牌色链接改 ink |
| 次文本 | `11px var(--muted)` 单行（`--list-meta-size`） | |
| 行内主操作 | `.row-action-link`：品牌色 `fw600 13px` 文本 | 消灭 `.btn-link`/`.btn-sm`/裸 `a` 三形态 |
| 分页句式 | 「共 N 条 · 第 x / y 页」+ 每页 select | V2 Pagination 收编（FL-D806） |

## 6. 微调记档（施工中续记；格式：处 | 原值→新值 | 理由）

| 处 | 原值 → 新值 | 理由 |
| --- | --- | --- |
| V1 body 字体族 | `"Segoe UI","Microsoft YaHei UI","PingFang SC"` → `--font-ui` | FL-D803 双轨统一 |
| gg-table hover | `#fdfbf9` → `var(--surface-soft)` | 消除第二色温 |
| 控件 hover 边 | V2 `#aeb8c1` → `#aeb7c0` | 近色并值（与 V1 按钮域一致） |
| 占位文本 | 浏览器默认 → `#98a1a9` | 层级与可读性 |
| V2 form-stack input 圆角 | `8px` → `6px` | 控件圆角统一 |
| V1 `.btn-link` 字重 | `700` → `600` | 行内主操作统一规格 |
| V2 `.status-badge` | fw650+二次覆盖(border,3px 8px) → 令牌规格(650,3px 9px,无边框) | 徽标双形态消灭 |
