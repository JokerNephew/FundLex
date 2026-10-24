# React V2 原版功能与入口对账矩阵

日期：2026-10-24

本矩阵以 Git 基线中的静态工作台 `frontend/index.html`、`frontend/app.js`、`frontend/app.css`、`frontend/compare.*` 为原版基线。React V2 只有在用户可以从工作台入口进入、通过真实 API 完成同等操作，并在目标视口可用时才记为等价。

| 原版能力 | 原版入口 | React V2 当前入口 | API/后端支持 | 当前状态 | 修复/验证阶段 |
|---|---|---|---|---|---|
| 登录、注册、退出、会话失效、修改密码 | 登录层、顶栏、修改密码 | `/` 登录层、`/settings` | 已支持 | 已迁移；临时服务浏览器回归通过 | 功能回归 |
| 广发基金 Logo 与 favicon | 顶栏、登录层、浏览器标签 | `/static/assets/gf-logo-mark.png`、`gf-favicon.png` | 静态资源已存在 | 已恢复并通过静态资源/入口检查 | 品牌回归 |
| 任务总览统计、搜索、状态/指引筛选、排序、分页 | `#overview` | `/tasks` | 已支持 | 已迁移；统计维度已补齐并通过类型/浏览器回归 | 功能/视觉回归 |
| 新建任务、多文件、文件夹、拖放、分块上传 | `#import` | `/tasks/new` | 已支持 | 已迁移 | 真实上传回归 |
| 上传清单搜索、状态筛选、分页、替换、移除、清空 | 新建任务文件表 | `/tasks/new` | 上传接口支持 manifest | 已迁移；搜索/异常筛选/分页/重复名保护/替换失败清除旧行均已验证 | 上传清单阶段 |
| 失败补传、待补传 CSV、任务详情重新进入上传 | `#import` recovery | `/tasks/:taskId` → `/tasks/new?taskId=...` | 已支持追加上传 | 已迁移；真实部分上传任务恢复、manifest 匹配和待补传 CSV 已验证 | 上传恢复阶段 |
| 任务详情阶段、进度、状态图例、暂停/恢复 | `#task` | `/tasks/:taskId`、`/tasks/detail` | 已支持 | 已迁移；阶段轨道、图例、暂停/恢复和异常筛选已验证 | 任务详情阶段 |
| 结果 CSV、汇总 Markdown、全部 ZIP | 任务详情操作栏 | `/tasks/:taskId` | 汇总/ZIP已支持，CSV可由分页结果生成 | 已迁移；三类入口与授权下载错误态已验证 | 交付下载阶段 |
| 合同详情、资格证据、目标、原文/新文、例外 | 详情遮罩 | `/tasks/:taskId/documents/:documentId/detail` | 已支持 | 已迁移；详情/报告/交付状态和错误态已验证 | 合同详情阶段 |
| final、redline、working、selected、报告下载 | 详情与 Review | 合同详情、任务详情快捷操作 | 已支持 | 已迁移；文件类型、授权入口和错误反馈已验证 | 下载回归 |
| Review 逐条/批量接受拒绝、导航、选择版 | Review 遮罩 | `/tasks/:taskId/documents/:documentId/review` | 已支持 | 已迁移；逐条/批量、导航、选择版和缓存刷新已验证 | Review 阶段 |
| 指引上传、解析、重解析、问题、启用、恢复默认 | `#guide` | `/guides`、`/guides/:guideId` | 已支持 | 本轮补显式重解析与 JSON 下载 | 指引阶段 |
| 开发设置与身份隔离 | `#settings` | `/settings` | dev/password 能力已支持 | 已迁移；dev/password 入口与身份重置保护已验证 | 认证阶段 |
| 管理员用户管理 | `#users` | `/users` | 已支持 | 已迁移；真实 API 请求、创建、启用/禁用和权限错误态已验证 | 管理员阶段 |
| 任务状态通知、数量徽标、跳转任务 | 顶栏消息中心 | 顶栏消息中心 | 任务轮询已支持 | 已迁移；任务状态轮询、徽标、消息跳转和身份清空已验证 | 壳层阶段 |
| 帮助中心、状态/安全/数据范围说明 | 页脚帮助 | 页脚帮助 | 无需 API | 已迁移；帮助内容、弹层关闭和焦点返回已验证 | 壳层阶段 |
| 合同对比完整工作台 | `#compare` / `/compare` | `/compare` 独立入口 | Compare API/Worker 已支持 | 原版功能可达；未纳入 React hooks/route，明确保留为独立工作台 | Compare 专项阶段 |
| 固定壳层、原版滚动模型、1180/760/420 断点 | 全局 | `AppShell` 与 `src/styles/app.css` | 不适用 | 已通过 1440/1180/1000/768/760/420/390 七视口无横向溢出检查 | 多视口阶段 |

## 阶段阻断条件

- “部分缺失”“只能通过旧页面绕路”或“在目标视口不可用”的条目不能标记为通过。
- Compare 当前保留独立页面是已知架构决策；在 React V2 总体验收中必须同时验证 `/compare` 从 React 导航进入后，完整独立功能仍可达且返回新版工作台入口正常。
- 最终发布前必须完成 1440、1180、1000、768、760、420、390 宽度检查，并沿真实登录、上传、Worker、产物、Review、下载路径验证。

## 本轮验证证据（2026-10-24）

- `PATH=/tmp/opencode/node-v20.18.0-linux-x64/bin:$PATH npm run typecheck && npm run lint && npm run build` 通过；最终发布资源为 `frontend/dist/assets/index-ko73k-L5.css`、`frontend/dist/assets/index-BkJEWrna.js`，`index.html`、CSS、JS SHA-256 已记录在 `ACTIVE_HANDOFF.md`。
- `FUNDLEX_BROWSER_TESTS=1 .venv/bin/python -m pytest tests/browser/test_frontend_v2.py -q`：**7 passed**；覆盖 React 入口、真实 DOCX 上传、任务/Review 深链、上传清单搜索/状态筛选/分页、Compare 独立入口、替换失败边界及桌面到768px原地缩放。
- `.venv/bin/python -m pytest tests/test_compare_*.py -q`：**70 passed / 5 skipped**；`tools/evaluation/compare_e2e.py` 使用 `/compare#compare` 后，独立 Compare 浏览器验收 **9/9 场景通过**，证据 `/tmp/opencode/compare-e2e-final.json`。
- 七视口本地检查：1440、1180、1000、768、760、420、390 均通过，`document.body` 与 `document.documentElement` 无横向溢出；另增加 1440px 原地调整到 768px 的收缩回归。公网 smoke 同样通过1440/768/390及原地收缩路径。
- 最终候选已受控发布到 `/opt/fundlex-recall-first/frontend/dist`，只重启 `fundlex-recall-api.service`，未重启 Recall Worker。公网证据为 `/tmp/opencode/fundlex-public-v2-smoke-published-fixed-20261024/result.json`；本轮前端发布未新增生产模型调用，真实合同交付另行验收。
