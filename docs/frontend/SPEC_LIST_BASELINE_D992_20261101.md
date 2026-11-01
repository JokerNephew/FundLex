# FL-D992 合同修改列表基准规格（用户拍板基准，2026-11-01）

> 用户拍板口径：「以合同修改的为模板，列不用一样多，字体要一致，查看按钮和它一致」。
> 实测对象：V2 合同修改任务列表 `frontend/src/pages/Tasks/index.tsx` 的 `data-table`（当前 working tree @ d805f40，dist 自拍 1440×900）。
> 实测脚本 /tmp/opencode/qa/proof/d992_baseline.py → 原始数据 /tmp/opencode/qa/proof/d992/{computed.json, v2-tasks.png}。

## 基准一：行名字体（列表任务名列）

| 属性 | computed 值 | 断言式规格 |
| --- | --- | --- |
| font-family | Inter, "PingFang SC", "Microsoft YaHei UI", "Noto Sans SC", system-ui, sans-serif | 全站所有列表的任务/文件名文字字体必须解析为同族（Inter 首发，中文回退 PingFang/YaHei/Noto，不得出现 serif 或自造字体覆盖） |
| font-size | 13px | == 13px |
| font-weight | 600（`<strong>`） | == 600（粗排文件名） |
| line-height | 20.8px（1.6 倍自然行高） | 不强制，但不得使用 < 1.2 压缩行高 |
| color | rgb(32,37,43)（--ink） | == ink 主色 |

## 基准二：单元格正文与表头

| 项 | computed 值 | 断言式规格 |
| --- | --- | --- |
| 单元格正文 | 13px / 400 / rgb(32,37,43) / Inter 族 | 列表正文一律 13px/400 |
| 表头 th | 12px / 600 / rgb(104,113,124)（--muted） | 表头一律 12px/600/muted |
| 次要小字（如「异常 0」） | muted 色即可，字号 ≤ 12px | 与单元格同字族 |

## 基准三：状态徽标与截断（FL-D992 用户指摘「状态太长超出宽度」的治本规则）

| 属性 | computed 值 | 断言式规格 |
| --- | --- | --- |
| font-size/weight | 11px / 650 | 徽标文案统一 11px/650 |
| max-width | 100%（相对单元格） | 徽标必须有上限 + `overflow:hidden` + `text-overflow:ellipsis`；最长徽标「已完成（部分需人工核对）」（=completed\_with\_exceptions）渲染宽不得超过单元格宽，`scrollWidth ≤ clientWidth` |
| white-space | nowrap | 徽标一律 nowrap，不许折行顶爆行高 |

## 基准四：「查看」按钮（用户点名统一对象）

| 属性 | computed 值 | 断言式规格 |
| --- | --- | --- |
| 形态 | `.table-link`（裸文本按钮，无框无底） | 全站列表行末操作统一为裸文本链接按钮（原生 `<a>` 或 `<button class="table-link">`），禁止 primary/secondary 实心按钮占行末 |
| font-size / weight | 13px / 600 | == 13px/600 |
| color | rgb(32,37,43)（list）+ hover 下划线 | 文本链默认主墨色，hover 加下划线（.table-link 既有行为） |
| padding / border / background | 0 / 0 / transparent | == 0 内边距、无边框、无底色 |
| display | inline | 不撑单元格 |

## 附：V1 对照口径（V1 `#task-rows`）

V1 侧同规格基准 = `.filename`（600 加粗）+ `.badge` + `.btn-link`（D881 已定「文件名加粗+徽标+btn-link」方言）。V1/V2 属同一模板的两种实现，各线以此规格核对，不要求列数一致（用户明确「列不用一样多」）。

## 使用方式

比对/指引生成等其他列表统一时：列结构自由，但**文本字体族、文件名 13px/600、正文 13px/400、表头 12px/600/muted、徽标 11px/650 带 ellipsis 上限、行末「查看」裸文本链**六条必须全部 ✅；验收断言直接按本文件属性表写 computed style 检查。
