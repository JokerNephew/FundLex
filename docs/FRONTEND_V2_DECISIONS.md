# FundLex Frontend V2 设计决策

日期：2026-10-25

## D-001 Review 默认 pending

所有未决 revision 必须是 `pending`，任何 pending 阻止 selected artifact generation。已实施于现有运行逻辑；本轮补齐按钮状态与持久化回归。

## D-002 Server State 使用 TanStack Query

TanStack Query 负责 server state；迁移完成后移除长期共存的自研 query cache。

## D-003 Zustand 边界

Zustand 只保存 auth/session、Review/Compare workspace 和本地 UI 状态；server object 的事实源由 query 保持。

## D-004 Compare 最终 React 化

最终入口为 `/compare` React route。legacy 页面只在明确的迁移期间作为安全 fallback，不能作为最终架构。

## D-005 New Task 是动作

新建任务通过任务页主按钮进入，不作为一级导航。

## D-006 不部署生产

本轮开发与验收不得部署生产。生产历史发布证据仅作为基线，不能替代本轮验证。

## D-007 最终验证依赖 Full-Stack Test Environment

壳层、fixture、隔离 worker 和 unit/component 不能替代真实普通用户端到端交付。真实环境不可用时保持 `BLOCKED`。

## D-008 文档先记录事实再记录结论

本轮所有新问题写入 `FRONTEND_V2_AUDIT_LOG.md` 和集中 `DETAIL_ISSUES_AND_RESOLUTIONS.md`；审计、实现、验证、发布分别标注，历史证据不回写为当前通过。
