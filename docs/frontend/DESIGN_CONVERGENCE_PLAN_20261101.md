# FundLex 全局设计语言收敛——施工规划（2026-11-01，第三轮需求）

> 依据：`docs/USER_REQUIREMENTS_20261101_SESSION2.md` 末尾「第三轮需求」（用户确认解读版）。
> 施工线：qa-frontend-s2-20261101（分支 `qa-frontend-s2-20261101`，基线 57290d4）。编号池 FL-D803~819。
> 上轮教训（主线自省）：错把 token 一致当验收。**本轮验收 = 全站逐页走查 + 全列表并排对照截图 + 逐项断言**，不接受"已用同 token"口径。
> 取证截图：`/tmp/opencode/qa/screenshots/design-audit-20261101/`（真实种子数据，非 mock 渲染）。

## 一、现状问题清单（按页·含证据）

### 1.1 列表统一（追责项）—— 实测五处列表四种语言

| # | 列表 | 实现 | 实测差异（证据） |
| --- | --- | --- | --- |
| L1 | V1 工作台·全部任务 | `.table`+`--list-*` | 字体 Segoe UI 系（`body{font:14px "Segoe UI","Microsoft YaHei UI",...}`，app.css:2）；任务名黑粗体 |
| L2 | V1 合同修改·修改任务 | `.table` 同上 | 同 L1；行尾「查看」=品牌色文本链接 `.btn-link`（fw700）；select 原生样式无 chevron（图 `input-v1-rest.png`） |
| L3 | V1 指引生成·任务列表 | `.gg-table` **独立散写** | 表体 12px（其余 13px）；td padding 12px（token 10/12）；hover `#fdfbf9`（token `--surface-soft`=#f7f9fa 异值无异名）；容器自画圆角边框；行尾「查看」=框式 `.btn-sm`（guide_generation.css:36/50-54，图 `list-v1-generation.png`） |
| L4 | V2 任务清单 | `.data-table`+tokens | 字体 Inter/Noto Sans SC（tokens.css:2）；任务名=品牌色加粗链接（app.css:41 fw650）；自定义 chevron（图 `list-v2-tasks.png`） |
| L5 | V1 合同比对·合同组 | `.compare-pair-status` 自定义卡条 | 按钮式卡条、圆点编号，非行语言（compare.js:74） |

**实证差异断言（浏览器真数据截图对照）**：①V1/V2 字体族不同→同 13px 视觉字号不同（用户"字体不同"根因，FL-D803）；②L3 与全站规格三处异值（FL-D804）；③行内操作组件三种形态：`.btn-link` 文本 / `.btn-sm` 框式 / V2 品牌色链接（行内组件不统一）；④徽标 V1 `.badge`(fw700，app.css:4) vs V2 `.status-badge`(fw650+border 二次覆盖，src/styles/app.css:28/155)（FL-D811）；⑤V2 `Pagination` 组件句式「第 1 / 2 页」与批2 统一句式「共 N 条 · 第 x / y 页」不一致（tests/browser/test_frontend_v2.py:503 锚定旧句式，FL-D806）；⑥L5 卡条选择器游离列表语言（FL-D805）。

### 1.2 输入框/下拉框（用户"很丑"）—— V1 无状态态 + 双形态不一致

| 状态 | V1（app.css:4） | V2（src/styles/app.css:126-130） | 判定 |
| --- | --- | --- | --- |
| rest | 1px `#cfd5db` / radius 6px / h36 | 同左 | 一致 |
| hover | **无** | border `#aeb8c1` | V1 缺（FL-D807，图 input-v1-hover.png） |
| focus | **无环无边色** | border brand+ring | V1 缺（图 input-v1-focus.png 与 rest 无视觉差别） |
| select 形 | **原生、无 chevron** | 自定义 `.ui-select` chevron | 双形态（图 input-v1-rest vs input-v2-rest） |
| 占位色 | 浏览器默认 | 浏览器默认 | 两形态皆未规格化 |
| 选项行高/选中态/滚动 | 原生 | 原生 | 用户要求规格化 |
| V2 内部 | `.form-stack input` radius **8px**（line 61） vs 全局 6px | | V2 自身分裂（FL-D808） |

### 1.3 动效（无统一规格）—— 十余种散写

实测（grep 全量）：时长 `.12s/.15s/.16s/.05s` 混杂；缓动 `ease` 与浏览器默认混排；一处 `none!important`（过渡禁用硬编码）；`width/height` 盒尺寸 transition 2 处（布局抖动源）；**弹层开合 0 动效**（`.detail-overlay`/guide-overlay 显隐瞬切）；**页面切换 0 动效**（`.section{display:none}` 瞬切）；孤立动画：`toast-in .18s ease-out`、`feishu-pulse 1.4s`、V2 `spin .7s` 三套自造语言；`prefers-reduced-motion` 仅 toast 一处（FL-D809/810）。

### 1.4 简约三禁令——逐页审计初判（批4 逐条执行）

- **删**：V1 overview「第一次使用？三步完成批量合同处理」卡（compare.html:253，常驻所有人可见，空态已有引导）→ 删卡，内容并入任务列表空态（FL-D812）。
- **删折叠**：`#compare .compare-groups-disclosure`「查看与切换全部合同组」折叠（compare.html:582）→ 平铺直呈（FL-D813）。
- **删折叠**：`.tech` 技术细节 `<details>`（JSON dump 信息藏）→ 删；有真实诊断价值的字段转一行明文（FL-D815）。
- **废话小字**：compare.html 现存 23 处 `.subnote`——逐条裁决，典型删除：「管理自己的指引版本…不能自动替换当前版本」（系统语义复述）；「尚未选择文件」占位重复。保留（有用户行动语义）：「Secret 会加密保存…不写入日志」「报告与诊断文件不作为最终合同（法务）」（FL-D814）。
- V2：逐页同审（Tasks 统计卡已批2 收敛；Guides/Settings/NewTask 待审）。

### 1.5 颜色微调（预登记，施工中逐条续记）

| 处 | 原值 → 新值 | 理由 |
| --- | --- | --- |
| gg-table hover | `#fdfbf9` → `var(--surface-soft)` `#f7f9fa` | 消除第二色温，token 归一 |
| select/input hover 边 | V2 `#aeb8c1` → `#aeb7c0`（与 V1 `.btn:hover` 统一） | 消除近色双值 |
| 占位文本 | 默认 → `#98a1a9`（`--muted` 淡阶） | 可读性与层级 |
| （允许项，施工中若触发到记） | | |

## 二、动效令牌表（唯一规格，全站只此一套）

写入两端令牌源（V1 `app.css :root` 与 V2 `tokens.css` 镜像），文档档 `docs/frontend/`。施工中禁页面级散写 transition。

| 令牌 | 值 | 用途 |
| --- | --- | --- |
| `--dur-fast` | `120ms` | hover 底色/边框微反馈 |
| `--dur-med` | `200ms` | 常规状态过渡（边框/阴影/颜色/透明度） |
| `--dur-slow` | `250ms` | 弹层/抽屉开合 |
| `--dur-press` | `50ms` | 按钮按压位移 |
| `--ease-standard` | `cubic-bezier(.2,.6,.25,1)` | **全站唯一缓动**（spinner/pulse 等无限动画允许 `linear`） |
| 允许属性集 | `background-color, border-color, color, box-shadow, opacity, transform` | **禁 width/height 盒尺寸动画**（布局抖动源），现状 2 处消灭 |
| 页面进场 | opacity 0→1 + translateY(4px→0)，200ms standard | V1 `.section` 与 V2 路由视图统一 |
| 卡片/列表 | 不做逐行 stagger（克制）；渲染贴入即时 | 禁第二种"亮相"风格 |
| 弹层开合 | 背板 fade 200ms；面板 translateX/scale 250ms（进）150ms（出） | detail/guide/help/password/notification 全部弹层统一 |
| 加载 | 唯一 spinner：V2 `spin .7s linear infinite` 收编至令牌，V1 文本加载态同风格 | 消灭自创加载语言 |
| 成败反馈 | toast slide-up 200ms + 状态色左边条（现制保留，时长归一 200ms） | |
| reduced-motion | 全局关闭动画与过渡 | 现仅 toast 有，补全站 |

## 三、组件令牌表（input/select 全状态矩阵 + 列表规格 + 徽标）

### 3.1 表单控件（V1/V2 唯一规格，列即验收断言项）

| 令牌 | 值 | 说明 |
| --- | --- | --- |
| `--ctl-border` | `1px solid var(--line-strong)`(#cfd5db) | rest |
| `--ctl-border-hover` | `1px solid #aeb7c0` | hover（V2 原 `#aeb8c1` 记档微调） |
| `--ctl-border-focus` | `1px solid var(--accent)` + `--ctl-focus-ring: 0 0 0 3px rgba(181,71,30,.14)` | **V1 新增**（现无聚焦态） |
| `--ctl-radius` | `6px` | 统一（消灭 V2 form-stack 8px 分裂，记档） |
| `--ctl-height` | `36px` / padding `6px 10px` | 输入与下拉同高 |
| `--ctl-placeholder-color` | `#98a1a9` | 双端统一 |
| `--ctl-disabled` | bg `#f5f6f8` + color `var(--muted)` + 去 hover | |
| select chevron | 唯一 SVG 数据链 + `appearance:none` + `padding-right:30px` | **V1 补自定义化**，消除原生/自定义双形态 |
| 原生 option（保留 select） | option 行高 `min-height:28px`；`option:checked` 色 accent-soft | 可样式化部分规格化 |
| 滚动容器 | 长 select 外层 `max-height:260px; overflow:auto; border-radius:6px` | 满足用户"滚动容器"项 |

### 3.2 列表统一规格（追责项·逐项断言清单）

| 项 | 唯一规格 | 消灭的差异 |
| --- | --- | --- |
| 字体族 | `Inter,"PingFang SC","Microsoft YaHei UI","Noto Sans SC",system-ui,sans-serif` | V1 Segoe UI 系退场（记档） |
| 表体/表头字号 | `13px` / `12px 600` | gg-table 12px |
| cell padding | `10px 12px` | gg-table 12px |
| hover 行 | `var(--surface-soft)` | gg `#fdfbf9` |
| 主键文本 | fw600 `--ink`，截断 title | V2 品牌色链接改 ink+下划线 hover（品牌色保留徽标与主按钮） |
| 次文本 | `11px var(--muted)` 单行 | |
| 行内主操作 | 唯一 `.row-action-link`：品牌色 fw600 文本 | 消灭 `.btn-link`/`.btn-sm`/裸 a 三形态 |
| 徽标 | `--badge-*`：pill / `11px` / `fw650` / `padding 3px 9px` / 无 border | V2 二次覆盖删除（记档） |
| 分页 | 唯一句式「共 N 条 · 第 x / y 页」+ 每页 select 20/50/100 | V2 Pagination 组件收敛（测试锚改语义断言） |
| `.gg-table` | **类别废除**，改 `.table` 体系 | FL-D804 |
| compare 合同组 | 重设计为列表行（编号+双侧文件名+状态徽标 行内布局） | FL-D805 |

## 四、分批施工计划（每批满配证据；末批含全站逐页走查+全列表并排对照截图）

| 批 | 内容 | 验收 |
| --- | --- | --- |
| 批0 | 令牌落档 `docs/frontend/DESIGN_TOKENS_20261101.md` + V1/V2 两端令牌镜像（不动样式） | grep 令牌引用率 |
| 批1 | 动效系统：散写收敛、弹层开合、页面进场、reduced-motion 全站 | node --check、渲染走查（开合截屏）、锥形 grep=唯一令牌值 |
| 批2 | 表单控件矩阵：V1 补 hover/focus、chevron 统一、占位/禁用/选项/滚动，V2 form-stack 分裂修复 | 三态截图对照（before 已存）、vitest/tsc/build |
| 批3 | 列表统一追责：字体族、gg-table 收编、徽标、行内操作、V2 分页句式、compare 合同组行化 | **五类列表并排截图+逐项断言首轮**、受影响套件 |
| 批4 | 三禁令逐页执行：第一次使用卡、compare 折叠、.tech 折叠、subnote 逐条裁决、V2 同审 | 每页 before/after；删后锚点复跑 |
| 批5（末批收口） | **全站逐页走查（V1/V2 全页面+弹层+空/错态）+ 全列表并排对照截图 + 逐项断言终版 + 整批回归**；颜色记档总表 | 对照图与断言表入档 docs/frontend/DESIGN_CONVERGENCE_ACCEPTANCE_20261101.md |

**施工纪律**：每批 commit 独立可合并；过期断言按 FL-D733 口径改语义锚（记集中册）；V1/V2 worker（ivRkf1jH/81FirpsQ）自批2 起派活：ivRkf1jH=V1 静态页域（compare/guide/generation)、81FirpsQ=V2 React 页域，我承担令牌源、V1 核心与全批次验收。

**状态**：规划完成待主线过目；FL-D803~815 已随本文登记（见集中册）。
