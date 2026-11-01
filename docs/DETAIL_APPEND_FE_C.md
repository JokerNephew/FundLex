# FE-C 线施工登记（qa-frontend-c-20261101）

登记纪律：本线只更新已赐号条目的施工/验证状态；新发现先向主线申请号段，不自封编号。

## FL-D989 飞书绑定独立页面（2026-11-01，done→待主线验收）
- 原话：「飞书绑定单独一个页面，不要把账户的修改跟他放一起」。
- 施工：
  - V1（生产 vanilla）：`frontend/compare.html` 飞书块（连接卡+三步指引+企业自建应用向导，含全部原 id）整体移入新 `<section id="view-feishu">`；侧边栏新增「飞书绑定」导航（新 `i-link` 图标）；设置页只留账户卡+「前往飞书绑定」跳转卡。`frontend/app.js`：`VIEW_TITLES` 增 `feishu`，飞书绑定/企业应用/OAuth 全部视图门控（L231/284/288/289/433/586/587/688/703）由 `settings` 改为 `feishu`，路由 `#feishu` 直达。
  - V2（React）：新页 `frontend/src/pages/Settings/FeishuBinding.tsx`（承接原绑定/扫码/解绑全部逻辑），`App.tsx` 增 `/feishu` 路由，`AppShell.tsx` 配置组增「飞书绑定」导航项；`Settings/index.tsx` 移除飞书全部状态与卡片，改放跳转卡，副标「管理账号安全和飞书接入」→「管理账号安全」。
- 验证：vitest 24/24 ✅、`npm run build` ✅、tsc ✅；截图：V1 设置页（无飞书）`/tmp/opencode/qa/feec-shots/after-settings.png`；V1 飞书独立页三态 `after-feishu-unbound/bound/unconfigured.png`；V2 `v2-settings.png`、`v2-feishu-unbound.png`、`v2-feishu-bound.png`。

## FL-D990 任务详情指引快照去红标+删「已锁定」（2026-11-01，done→待主线验收）
- 红标元素级定位：`.task-guide-meta`（compare.html:355 「使用的修改指引」条）的 `border-left:3px solid var(--accent)`（--accent=#b5471e 橙红）与底色——app.css:853。「已锁定」= app.js:251 `guideNameForTask()` 模板尾巴。
- 施工：app.js `guideNameForTask` 只回文件名（fallback「创建时的指引」不变）；app.css `.task-guide-meta` 去红左边条、底色与圆角，成普通一行；V2 侧照 s2 未并入树最新思路（`使用《filename》`）在我树 React `TaskDetail/index.tsx` 落地：页头 `创建于 … · 使用《文件名》`，无红标无「已锁定」，legacy/未绑定回退保留。
- 验证：截图对照 `before-task-detail.png`（红条+「· 已锁定」）vs `after-task-detail.png`（纯文件名一行）。vitest/build 绿。

## FL-D994 删「仅合同修改任务；全部三类业务任务见 工作台 · 全部任务」（2026-11-01，done→待主线验收）
- 定位说明：主线看板记「在生产构建 index-N7wocR2n.js」，实测该 bundle 已于 2026-11-01 18:55 被他线重建、不含此文案；正源为 V1 生产页 `frontend/compare.html:155`（与生产 /opt 同文件已核对 md5 一致），直删 `<small>` 元素。
- 验证：截图对照 `before-overview.png`（有小字）vs `after-overview.png`（无）。vitest/build 绿。

## FL-D992 Tasks 部分：修改任务列表状态列溢出（2026-11-01，done→待主线验收）
- 范围声明：只修「修改任务」列表（app.js `taskRow()`），基准字形（badge 字号/字重/配色、查看按钮）未动。
- 施工：`taskRow` 状态 `<td>` 加 `class="task-status-cell"` 与 `title`（完整状态文案）；app.css 新增 `.task-list-table .task-status-cell .badge{display:inline-block;max-width:10em;overflow:hidden;text-overflow:ellipsis;vertical-align:middle}`。
- 验证：截图 long-status 用例（completed_with_exceptions=「处理完成（部分需人工核对）」）：`before-overview.png` 溢出侵入进度列 vs `after-overview.png` 省略号截断。vitest/build 绿。

## 账本
- 真实模型调用：0（纯前端施工，截图数据全部路由桩注入，未触发引擎/模型）。
- 截图环境：8076=qa-base 原版、8077=施工版 V1、8078=施工版 V2（均为 scratch sqlite + dev 身份，不触生产数据）。

## 双盲质检记录（2026-11-01，独立子agent）
- 结论：PASS（4/4 达标）。发现 P1（中）node_modules 软链误提交→162bc7d 已移出并复核 .gitignore 覆盖；P3（低）V2 飞书页卡内文案与页头重复→5a96ccd 已改并重拍 v2 截图；P2（低）V2 飞书页未含 V1 企业自建应用向导——系 V2 原有功能缺口（原 V2 Settings 即无向导），非本次回归，提请主线赐号立项跟踪后再登记。
