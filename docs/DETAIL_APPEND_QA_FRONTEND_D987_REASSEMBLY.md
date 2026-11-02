# 新发现登记（qa-frontend·重组装附件）——待主线申请号段后再入集中册

> 本文件遵循项目规定「新发现先向主线申请号段再登记」，文中问题无自封编号。
> 发现日期：2026-11-02（zip blind 质检报出，重组装分支 qa-frontend-reassembly-20261102 已观察）。

## 建议新增 1（**作废**——V2 已随 FL-D1010 物理删除，本条目仅留档不入册）

原问题（重组装-2 中 V2 CompareTaskPage 的 viewerDismissed 在 browser back/直改 URL 换 pair 路径不重置）已被「V2(React) 前端物理删除」的用户裁决整机消解；不迁移到 V1（V1 chip 组切换走 dialog 内按钮 + URL 换 pair 由 openTask 轮询重开，无同款边界）。

## 建议新增 2（低） V1 轮询路径 openTask 对 viewer hidden=false 无 backdrop/bodylock 补发

- **现象**：qa-frontend-reassembly-1 中，compare.js openTask() 内部轮询分支 `$('compare-viewer').hidden=false` 直接显 viewer——未走 setViewerOpen(true)，此时 backdrop 未同步可见、body lock 未上。条件：dialog 已点开+任务仍在 polling 的并发窗口。
- **影响**：viewer 显示但 backdrop/bodylock 缺失瞬间。
- **处理建议**：该处改为调用 setViewerOpen(true)（单一壳控制点）。
- **状态**：待主线号段登记。

## 建议新增 3（基线本体红，与重组装无关）

- **现象**：tests/browser/test_v1_frontend_remediation.py::test_v1_password_late_401_from_previous_account_does_not_logout_new_session 在干净基线 d734855（本刀未入的相关分支 stash 验证）即失败（`held` 拦截 30 秒空断言 997 行）。不是本刀引入。
- **处理建议**：主线自行裁决（属 settings/feishu 域，不在本线范围）。
- **状态**：仅呈请主线知悉。
