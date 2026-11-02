# Guides 域三案（FL-D988/D992/D993）第三任接棒·落地报告（2026-11-02）

> 接棒路径：FE-B 起源施工 → FE-D 落地 8 commit（基点 449cc5e，qa-frontend-d-20261102，'done 待主线验收'）→ 本线（qa-frontend-v2）按总指挥令**新开分支 qa-frontend-v2-20261102 @ 主线 HEAD d734855**，cherry-pick FE-D 8 件零冲突整合+顺手修 1 件既有 lint，过四闸+自拍截图，交验收。

## 0. 用户原话 → 断言表

| 案 | 用户原话 | 断言与判据 | 结论 | 证据 |
| --- | --- | --- | --- | --- |
| FL-D993 | 「修改指引页里面规则开关的子页面还是没删」 | 详情页无规则开关 Card/勾选/保存；列表无「查看规则与开关」入口；全页面无「规则开关/规则启停」文案；hooks/endpoints/types 客户端件清零；后端 API 零改动 | ✅ | grep「规则开关\|rule-settings\|useGuideRuleSettings\|GuideRuleSetting\|规则启停」src=**0**；截图 `d993-guide-detail.png`（解析结果/解析问题两卡+三按钮，无开关区块）；详情页内文本断言 `assert "规则开关" not in body` PASS；git diff 仅 `frontend/src|tests` |
| FL-D992 | Guides 列表对齐基准 | 行名/单元格/表头规格、状态长句收敛副注+title、徽标 max-width/ellipsis、「查看」裸文本链 | ✅ | FE-D computed 实测（基点树）+ 本树源码在档：`.status-badge max-width:100%/overflow:hidden/ellipsis`（app.css:22 行处）；状态列副注 11px muted+title 完整句（Guides/index.tsx 渲染）；「查看」为 `.data-table a` 裸链；截图 `d992-d993-guides-list.png`（两版行式、「查看 启用」列）+ 移动版 `d992-guides-list-mobile.png` |
| FL-D988 | 「指引生成相关子页面的风格明显和其他页面的风格不同」 | guide-diff-* 散写全部收编令牌层；色值/圆角/字号与结果页/任务页同谱；CompareCard 骨架同 page-heading/ui-card 类 | ✅ | FE-D 对照实测（基点树，两端逐值一致）+ 本树 app.css 散写抽检：guide-diff 相关仅剩 4 处**刻意 canonical 对齐**（`#b9e6c5`/`#f5b9b2`/`#b3261e` 插删/描红色值，与比对链 compare.css 逐字一致；FE-D 已登记 --word-red 上提令牌建议归主线裁决） |

## 1. 施工清单（8+1 commit，全部 cherry-pick 零冲突）

`403cc74` D993 主件（-213 行）→ `930370f` D988 缺文件不再回显英文 → `4916b21` D988 guide-diff-* 令牌收编 → `1d5124d` D992 状态长句副注 → `9322272` D988 原文比对 canonical 色 → `864435d` D992「查看」裸链 → `3a36be3` D992 徽标三治 → `1a417df` D988 解析问题空卡兜底 → **`STATUSLINT-fix`（本线顺手修）**：`CompareListPage.tsx` 删 `statusLabel` unused import（FE-D 新发现#1 上报的既有 lint error；其徽章传原始码一半已在主线，本补丁收尾另一半）。

## 2. 四闸与验证

- `npx tsc --noEmit` 0 错；`npx vitest run` 7 文件 **32/32 绿**（与 FE-D 基点持平，无退化；语义三件套 commit 232e5c1 未含语义增项属正常——35/35 基线见 qa-frontend-v2-20261101 旧支线）；`npm run build` ✓；`npm run lint` **0 error**（顺手修后，FE-D 遗留 1 error 清零）。
- 浏览器自拍断言（真实 Chromium+dev 服务+route 造假，截图回读复核）：列表页（D992 行式+D993 入口侧）、详情页（D993 无开关+解析问题兜底文案显现）、移动 390px 列表、`/tasks` 风格对照。证据 `docs/frontend/evidence/guides-20261102/`×4。
- **造数错误自纠记录**（勿误判为应用 bug）：①假数据 `created_at` 支持 epoch 或字符串均可渲 ②`Summary.groups/issues` 必须是数字（对象→React #31）③`detail` 同 ④diff 结构 `{diff:{summary,meta,validation:{before:{clean}},rules}}`、text-diff `{text_diff:{summary,left_html,right_html}}` ⑤`/api/settings/guide` 响应键是 `current`（非 current_version_id）。另记：Guides 页首载自动拉当前版 diff，响应空 `{}` 会白屏（假数据不完整所致，真实后端结构完整）。

## 3. 新发现（报主线申请号段，本线不自封）

- **N1（人话化映射漏 `needs_review`）**：`frontend/src/pages/Guides/index.tsx:27` `qualificationStatusText` 映射表（certified/frozen_builtin/not_run/failed）缺 **`needs_review`**——后端 `fundlex/guide_store.py:44/779` 实写 `QUALIFICATION_NEEDS_REVIEW="needs_review"` 入 `qualification_status`；详情页「可用状态」柱值会英文裸显（走查截图 `d993-guide-detail.png` 同款机位实证了「eligible」形态=未映射原样回显，`needs_review` 将同款）。建议中文映射「质量待复核」。**申请 FL 号段登记**。
- （非发现、仅说明）截图中「当前指引」卡显示「当前没有可用指引」系本线假数据键名错误（`current_version_id` vs 实际 `current`），凭 fundlex/api.py:801 证后端会返回 current 对象，真实场景不一。

## 4. 质量双保险

- A 自拍截图自检：§0/§2。
- B 子agent质检：⚠ 如实申报——环境工具集无 subagent（沿用 FL-D991 申报口径），已用 grep 清零+四闸+截图回读+假数据对照源码三重替代；**申请主线补派质检**（材料：`git diff d734855..HEAD`+本报告+截图目录+FE-D 登记 `docs/DETAIL_APPEND_FE_D.md`）。

## 5. 与 FE-D 的关系（不重复施工声明）

本线零新改设计：8 commit 全部 cherry-pick 自 `qa-frontend-d-20261102`（4fbc2ca/8dc8831/8c2e4c5/ef8faca/2f9d1d2/d71eca7/a4609d8/492cb3a），基点差异与冲突零。FE-D 注册的新发现处置：#1（lint）本线顺手修 解；#2（V1 规则开关删除件 46902a0 归属）维持主线裁决；#3（--word-red 上提）维持登记；#4（status-badge 上限面为全站）本报告按基准三口径随行。
