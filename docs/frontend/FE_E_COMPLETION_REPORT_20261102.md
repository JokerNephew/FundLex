# FE-E 六案完工报告（V1 表面战 · Guides/工作台域，2026-11-02）

> 施工线：FE-E · 工作树 `qa-frontend-e-20261102`（`.local/share/opencode/worktree/29a9a9/qa-frontend-e`）
> 全部改动在 **V1 静态页层**（`frontend/*.html/*.js/*.css`，用户日常实际使用路径）；未触 React/V2 层。
> 主线树 `/tmp/opencode/qa-base` 全程只读，未写。
> 施工 commit 两笔：`c614096`（①④⑤）、`9df4632`（③② + D894）。
> 验证双保险：Playwright 真实浏览器自拍（截图+computed style 断言）+ 独立子 agent 质检（两轮，均 PASS）。

## 一、截图断言对照表

### 案① FL-D993 规则开关子页面删除（用户原话："修改指引页里面规则开关的子页面还是没删"）

| 断言项 | before | after | 结果 |
| --- | --- | --- | --- |
| 指引页 tab 数 / 文案 | 3 个（指引版本/版本对比与上传/规则开关） | 2 个（指引版本/版本对比与上传） | ✅ |
| `#view-guide` 内出现"规则开关"字样 | 有 | 无（`hasRulesWord=false`，grep frontend V1 五文件零命中） | ✅ |
| `data-guide-pane="rules"` 元素 | 有 | 无（`rulesPane=false`） | ✅ |
| 指引列表行操作按钮 | 「规则开关」+「查看问题」 | 仅「查看问题」 | ✅ |
| 启停相关 JS 标识符残留 | 13 项 | 零命中（refreshGuideRulesVersion/loadGuideRulesInline/saveGuideRuleSettings/syncGuideRuleUI/guideRuleRow/guideRuleOpsSummary/guideRulesOverview/GUIDE_RULES_READY/guideRulesBox/data-guide-rule*/rule-settings） | ✅ |
| 指引详情弹层（查看问题） | 信息+规则开关+概览+问题 | 信息+规则概览+解析问题（只读三块保留） | ✅ |

截图：`/tmp/opencode/qa/fee-proof/01-guides-page.png`
compare.html 页头文案「启停规则开关，」字样同步清除（用户点名"compare.html 里也搜得到，一并清"）。

### 案④ FL-D990 任务详情页去红标+删「已锁定」（workbench/工作台侧；compare 侧归 CX 线）

| 断言项 | before | after | 结果 |
| --- | --- | --- | --- |
| 指引标注文案 | `销售费用新规修改指引V2.docx · 已锁定` | 纯文件名（`hasLockWord=false`） | ✅ |
| `.task-guide-meta` borderLeft | 3px accent（红/橙强调标注） | `0px` | ✅ |
| `.task-guide-meta` 背景 | `#f8f9fa` 底色块 | `rgba(0,0,0,0)`（纯文本行） | ✅ |
| 指引内容本身 | 显示 | 保留显示（用户：内容可保留） | ✅ |

截图：`/tmp/opencode/qa/fee-proof/03-task-detail.png`

### 案⑤ FL-D994 「仅合同修改任务…」文案删除

| 断言项 | before | after | 结果 |
| --- | --- | --- | --- |
| compare.html 修改任务卡头小字「仅合同修改任务；全部三类业务任务见 工作台 · 全部任务」 | 有 | 已删（`hasOldCopy=false`） | ✅ |
| V1 落点自查（frontend/*.js|*.html|*.css grep「仅合同修改任务」） | compare.html:165 | 零命中 | ✅ |

截图：`/tmp/opencode/qa/fee-proof/02-task-list.png`

### 案③ FL-D992 指引列表+任务列表基准（computed style 实测，1440×900）

基准来源：`docs/frontend/SPEC_LIST_BASELINE_D992_20261101.md`（用户拍板：以合同修改列表为模板，字体一致、查看按钮一致、状态徽标截断）。before/after 同机同视口自拍：

| 基准 | 规格 | 指引列表 before → after | 任务列表 before → after | 结果 |
| --- | --- | --- | --- | --- |
| ① 文件名字体族/13px/600 | Inter 族/13px/600 | Inter/13px/600（前后一致） | 同 | ✅ |
| ① 文件名颜色 == ink | rgb(32,37,43) | rgb(41,50,59) → **rgb(32,37,43)** | rgb(41,50,59) → **rgb(32,37,43)** | ✅（修 `.table .filename` 色值） |
| ② 单元格正文 13px/400/ink | == | 13px/400/ink（前后一致） | 同 | ✅ |
| ② 表头 12px/600/muted | == | 12px/600/rgb(104,113,124)（前后一致） | 同 | ✅ |
| ③ 徽标 11px/650 | == | 11px/650（前后一致） | 同 | ✅ |
| ③ 徽标截断上限 | max-width+hidden+ellipsis+nowrap | `maxW=none,overflow=visible,ellipsis=clip` → **`100%,hidden,ellipsis,nowrap`** | 同 | ✅（修 `.badge`，治"状态太长超出宽度"） |
| ④ 行末「查看」裸文本链 | btn-link 13px/600/ink、无边无底零内边距 | cls=btn-link ✓、pad=0/border=0 ✓、颜色 rgb(142,50,19) → **rgb(32,37,43)** | 同 | ✅（修 `.table .btn-link`） |

截图：`/tmp/opencode/qa/fee-proof/{before,after}/guides-list.png`、`task-list.png`、`task-detail-narrow.png`

### 案② FL-D988 指引生成域风格统一（V1 落地）

| 断言项 | 实测值（after） | 结果 |
| --- | --- | --- |
| 列表卡片阴影 | `--shadow`（rgba(34,40,48,.05) 0 4px 18px），与 app `.card` 一致 | ✅ |
| 任务名（首列 strong） | Inter 族/13px/**600**/rgb(32,37,43)——与 D992 文件名基准一致（施工前为 700） | ✅ |
| 行末「查看」 | cls=btn-link，13px/600/ink 裸文本链 | ✅ |
| 表体系 | `.gg-table table` 收编 `.table`（th/td/hover 全走 token） | ✅ |
| 输入控件 | 命中 app.css 表单控件唯一状态矩阵（hover/focus ring/disabled） | ✅ |

截图：`/tmp/opencode/qa/fee-proof/04-generation-list.png`、`05-generation-new.png`

### 案⑥ FL-D894 技术内容外泄清扫（V1 域，补漏令①）

用户原话："页面中还有很多用户根本不需要看到的技术内容，比如'规则哈希5335e401e840…'"。全站判定与处置：

| 落点 | before | after | 判定 |
| --- | --- | --- | --- |
| 指引解析问题列表标题 | 裸英文码 `GUIDE_SLOT_NOT_IN_TEXT` 等（`<code>` 标题式） | 人读问题名（如「指引引用与原条款对不上」），错误码收折叠详情「问题代码」行 | ✅ 修 |
| 指引生成编辑器 | 裸 `<code>guide_item_id</code>` | 删（标题已含条目名） | ✅ 修 |
| 适用性问题行 | 裸 `guide_item_id · clause_id` | 按条目标题引用，编号收 title 悬浮 | ✅ 修 |
| 当前候选卡 | 裸 `candidate_version_id` 长 id | 收「高级详情」折叠（与历史版本卡既有做法一致） | ✅ 修 |
| 合同影响/补漏记录 | 裸 `impact_id`/`requirement_id`/候选条目 id 列表/影响筛选下拉裸码前缀 | 全部改按法规条文·条目标题引用（无标题回退 id） | ✅ 修（QA 观察项②追缴） |
| 修复建议文案 | 「槽位 token」 | 「占位标记」 | ✅ 修 |
| 阶段/轮次失败 error_code | `<details>技术信息</details>` 折叠内 | 保持折叠（藏起判定，支持追溯） | 保留 |
| 规则编号 `规则 R{id}`、要求编号（折叠 dl 内） | 呈现于人读语境 | 业务编号保留 | 保留 |
| model connection_id | 仅 `hidden` input | 不外显 | 保留 |

「各种小字很多…酌情删」结论：**V1 全域无 ≤10px 字号**（最小 11px，即 D992 允许的次要小字档），无需调字号；噪点小字随技术内容删除同步减。

前后对照截图：`/tmp/opencode/qa/fee-proof/{before,after}/guide-issues-overlay.png`
实测断言：`firstSummary` 由 `GUIDE_SLOT_NOT_IN_TEXT · …` → `指引引用与原条款对不上 · …`

## 二、子 agent 质检记录

| 轮次 | 范围 | 结论 |
| --- | --- | --- |
| 质检①（ses_e65fa48d3ffeivev7G9DEOBF4h） | commit c614096 diff：13 个待消失标识符零命中、HTML 标签配对校验、函数签名调用方一致、9 条失效 CSS 无引用、无误删（row-sub/GUIDE_ENABLEABLE/diff 逻辑/弹层三块完好） | **PASS** |
| 质检②（ses_e65dfacf4ffe9pcTfDYVcVFVBQ） | commit 9df4632 diff：模板字符串闭合/TDZ、作用域一致、裸码残留 4 处全在折叠语境内（有意保留）、CSS 花括号配平、docs 条目格式一致 | **PASS**（观察项①徽标软截断可接受；观察项②影响域裸 id 已当轮追缴修复） |

## 三、入册情况

`docs/DETAIL_ISSUES_AND_RESOLUTIONS.md`：FL-D988/D990/D992/D993/D994 各追加 FE-E 跟进（含证据路径与验证结论）；新建 **FL-D894** 条目（处置清单、保留判定、小字清扫结论、下一步）。

## 四、边界与移交

- compare.js 侧：案④ compare 域 + D894 同类外泄排查归 **CX 线**（条已注）。
- 案①③④⑤ 的 V2 React 层/生产构建残留（Guides/index.tsx、index-N7wocR2n.js 等）归 **V2 线**。
- 观察项：`.badge` 为 inline-flex，ellipsis 是 soft-truncate（不溢出但部分浏览器省略号可能不渲染），生产巡检肉眼复核即可。
- 截图中 "Invalid Date" 为 mock 数据伪影，非代码回归。
- 本线未执行发布；合并/发布由主线统一走 `tools/deploy/publish_workspace.sh`。

## 五、复验指引

```bash
# 同机复拍（前后对照需 git stash 配合，见脚本头注释）
/home/opencode/fundlex/.venv/bin/python /tmp/opencode/qa/fee_proof.py
/home/opencode/fundlex/.venv/bin/python /tmp/opencode/qa/fee_gg.py
/home/opencode/fundlex/.venv/bin/python /tmp/opencode/qa/fee_d894.py after
```
证据目录：`/tmp/opencode/qa/fee-proof/`（`01..05-*.png`、`{before,after}/*.png`）。
