# Frontend V2 Full-Stack Test Environment Requirements

本文件是 Frontend V2 与并行 Full-Stack Test Environment 的接口边界。它只记录前端需要的环境契约，不修改测试环境部署、systemd、reverse proxy 或 secrets。

## Frontend build output

- `frontend/npm run typecheck`, `npm run lint`, `npm run build` 必须通过。
- 测试环境部署 `frontend/dist` 的 `index.html` 和 hashed assets，保留静态资源 MIME 与缓存策略。
- API 与前端使用同源 `/api`；Vite 本地可通过 `VITE_API_PROXY_TARGET` 代理，部署环境不依赖开发 server。

## SPA fallback

以下深链必须返回 React `index.html`，而非 404 或 legacy fallback：

- `/tasks`
- `/tasks/new`
- `/tasks/:taskId`
- `/tasks/:taskId/documents/:documentId/detail`
- `/tasks/:taskId/documents/:documentId/review`
- `/compare`
- `/guides`, `/guides/:guideId`, `/settings`, `/users`

API、静态 asset、授权下载路径不能被 SPA fallback 吞掉。

## Runtime environment indicator

前端需要读取 capabilities/version/health 的非秘密信息并显示当前环境（例如 `TEST · <commit>`）。不得向浏览器发送模型密钥、SSH 信息、数据库凭据或完整环境变量。

至少需要：

- frontend commit/build id
- API schema/app version
- test environment identifier
- worker availability/health（状态语义来自后端，不由前端猜测）
- active guide/version metadata

## Required API routes

### Auth

`GET /api/capabilities`、`POST /api/auth/login`、`POST /api/auth/register`（若启用）、`POST /api/auth/logout`、`GET /api/auth/me`、`POST /api/auth/password`。

### Tasks and artifacts

`POST/GET /api/tasks`、`GET /api/tasks/stats`、`GET /api/tasks/{id}`、`GET /api/tasks/{id}/documents`、`POST /api/tasks/{id}/uploads`、`POST /api/tasks/{id}/seal`、`POST /api/tasks/{id}/pause`、`POST /api/tasks/{id}/resume`、文档 report/revisions/decisions/accept-all/download，以及 task report/all download。

### Guides and admin

`GET/POST /api/guides`、guide detail/source/rules/parse、`GET/PUT /api/settings/guide`、管理员 users routes。

### Compare

`POST/GET /api/compare/tasks`、task/pairs/upload/seal、pair/view。React Compare 迁移后这些接口仍需同源、授权、owner isolation、失败和重试语义。

## Auth expectations

- Test 环境提供至少一个普通 password user 和一个 admin user；凭据通过受保护测试配置注入，不写仓库、不写截图、不写日志。
- 每条真实浏览器路径必须使用 password login；dev header 只用于本地/隔离测试并明确标注。
- 401 应使前端清除 token、query cache、workspace 并回登录；需要可控的 expired session 测试。
- 用户 A 不能查看 B 的 tasks、guides、artifacts、compare pairs 或报告。

## E2E corpus requirements

至少提供已授权的公开 DOCX：

1. 一份确有应改目标并能产出可核对修改的普通合同；
2. 一份有 unresolved/incomplete 或明确人工复核项的合同；
3. 一份长合同用于分页/Review 性能；
4. 一对有修改/插入/删除/零差异的 Compare 文档；
5. 文件名、源 SHA、授权范围、预期业务核对点和公开来源记录在测试环境证据中。

## Required real acceptance path

Browser → test frontend → password login → New Task → real DOCX → upload/seal → persistent Worker → real model path where required → report/artifacts → Document Detail → Review pending/accept/reject → selected artifact → authenticated download. 机械核验必须确认 DOCX zip、`word/document.xml`、artifact kind、Review decisions、SHA-256 和 report 一致。

Compare 还必须走 Browser → React `/compare` → pair upload/seal → compare worker → result/view → left/right coordinates → current diff connector → prev/next；若产品不提供 compare 下载，环境证据必须明确记录该契约。

## Evidence boundary

环境输出需同时保存 deployed commit、frontend build hash、API/worker build identity、task/document/compare IDs（可脱敏）、请求层级、artifact SHA、实际模型/Worker 证据、页面截图、console/network gate 和失败/阻塞原因。Fixture、controlled worker、临时 FastAPI、离线 replay 和 HTTP 200 单独标记，不能合并成 real business validation。
