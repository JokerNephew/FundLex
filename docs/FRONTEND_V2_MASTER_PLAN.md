# FundLex Frontend V2 最终整改主计划

日期：2026-10-25
分支：`feat/frontend-v2-final`
状态：`IN_PROGRESS`

## 1. 用户目标与范围

本计划承接 Frontend V2 最终整改要求：在保护现有真实业务能力的前提下，收敛 React + TypeScript + Vite 工作台的架构、状态、Review、Compare、响应式、可访问性和测试证据。范围包括 React 前端、最小 API 兼容调整、前端自动化测试和与 Full-Stack Test Environment 的集成要求；Recall/Generation 引擎不在本分支的默认范围内。

当前基线事实：HEAD `f59c452`，原始分支 `refactor/backend-engine-finalization`，已创建本分支；工作区存在用户已有未跟踪的 `docs/evidence/final-validation-20261022/` 证据，保持不动。React V2 源码位于 `frontend/src`，旧壳和独立 Compare 仍位于 `frontend/app.js`、`frontend/compare.js`。

## 2. 当前问题分级

### P0

- Review 未审阅项必须保持 `pending`，且 pending 必须阻止 selected artifact 生成。
- `working`、`redline`、`selected`、`final`、`report` 下载类型必须明确，`incomplete`、`unresolved`、`unsupported`、`failed` 不得被隐藏。
- DocumentViewer 保持 DOMParser + allow-list，生产路径禁止无审计 `dangerouslySetInnerHTML`。
- 前端测试证据必须区分壳层/fixture、真实 FastAPI、真实 Worker/model、真实 DOCX 产物。

### P1

- React V2 当前使用自研 query cache，缺少 TanStack Query 的失效、轮询和 mutation 统一语义。
- mutation、upload、download 收到 401 时未统一清理 auth、请求和 workspace 并回登录入口。
- Review 决策草稿只在内存中，刷新或离开页面会丢失。
- Review 生成按钮未直接反映 pending gate；移动端双向定位不能自动切换到目标面板。
- 任务详情 ZIP 下载条件比后端/原版严格，部分可下载结果可能被 UI 禁用。
- Compare 当前由 React 壳层通过原生链接进入 legacy HTML/JS，尚未完成 `/compare` React route。
- 任务级 current Worker phase 不能由当前分页某个 document 猜测；CSV 必须与 DocumentFilters 语义一致。

### P2

- 帮助 Dialog 焦点捕获、Escape 和恢复焦点需要统一。
- 全局 CSS 存在重复基础定义，需收敛 tokens/reset/layout 与模块样式。
- 需要统一 StatusBadge/reasonMeta、Dialog/Popover/Tabs/Table/Empty/Error/Loading 等设计系统组件。
- 需要完成 1440/1280/1000/768/420/390 视口、键盘、对比度、reduced-motion 和交互嵌套审计。

## 3. 已知必须保护的能力

- 真实 API、登录/注册/退出、任务查询和轮询。
- 多文件、文件夹、拖放、DOCX 校验、清单搜索/筛选/分页、重复检测、替换/移除/清空。
- 分块上传、进度、部分失败、待补传、client id、幂等和恢复任务。
- 任务详情、文档详情、资格/交付/异常状态、CSV/汇总/ZIP/合同产物下载。
- Review 的三态 `pending`/`accept`/`reject`、批量处理、正文 marker 与 revision card 双向定位。
- DocumentViewer 的 DOMParser allow-list。
- Guides、Settings、Users 和既有品牌资源。
- Compare 的 parser/worker/API、坐标、双栏阅读、导航和 owner 隔离能力。

## 4. Route Map

| Route | 页面 | 目标 |
|---|---|---|
| `/` | 登录/重定向 | password/dev auth 与 session 失效 |
| `/tasks` | 任务列表 | 搜索、筛选、排序、分页、inline metrics |
| `/tasks/new` | 新建任务 | 多文件上传、清单、恢复、提交 |
| `/tasks/:taskId` | 任务详情 | 真实 task aggregate、文档筛选和交付 |
| `/tasks/:taskId/documents/:documentId/detail` | 合同详情 | 目标、证据、异常、下载 |
| `/tasks/:taskId/documents/:documentId/review` | Review | pending-first、草稿、定位、selected gate |
| `/compare` | React Compare | 任务/文件对、结果、差异导航和下载/错误 |
| `/guides`、`/guides/:guideId` | 指引 | 解析、问题、启用、恢复默认 |
| `/settings` | 设置 | 账户、安全、系统环境 |
| `/users` | 用户管理 | Admin 用户隔离和状态 |

“新建任务”和任务详情不是一级导航；Compare 最终必须进入 React Router。

## 5. 状态架构目标

- TanStack Query 负责 API server state、query keys、缓存、失效、polling、mutation 和 retry。
- Zustand 只负责 auth/session 与 Review/Compare/local workspace state，不保存 server object 作为事实源。
- 统一 API client 对 query、mutation、upload、download 的 401 触发 session-expired 处理。
- 统一 `DocumentFilters` 和 `buildDocumentQuery` 用于文档列表、tabs、advanced filter、分页、URL 和 CSV。
- 页面只显示后端真实 phase；不能以当前分页 document 伪造 task-level phase。

## 6. Review 目标

- 所有新 revision 默认 `pending`，生成按钮在 `pendingCount > 0` 时 disabled，并保留服务端 gate。
- 草稿绑定 user/task/document/revision payload version/hash；payload 变化时失效并提示。
- 正文和 revision panel 独立滚动；点击任意一侧后 active anchor/card 和目标面板可见。
- A/R、方向键、输入控件避让、focus、aria 和 mobile tabs 可用。
- `selected` 生成后清理或标记对应草稿，下载类型清晰。

## 7. Compare 目标

先完成 legacy capability matrix：upload、pair、batch、job/status、result、diff type、coordinates、navigation、download、error/retry。随后将现有 `/api/compare/*` 接入 React Router，迁移双栏、SVG connector、差异列表、移动 tabs 和深链；在 React parity 与 browser/Full-Stack Test Environment 证据完成前保留安全 legacy fallback。

## 8. Design System / Responsive / Accessibility

使用品牌色 `#B5471E/#8E3213/#FFF1E9`，浅色 surface、1px border、有限 shadow、4px spacing grid 和系统字体。避免 SaaS dashboard/card wall、过量橙色、渐变、glass、emoji、全局 11px。统一 Button、IconButton、Input、Select、Tabs、Badge、StatusBadge、Dialog、Table、Pagination、Empty/Error/Loading、PageHeader、Toolbar、ProgressBar。

桌面 sidebar 220–236px；Review/Compare 优先全宽。<=760 使用 tabs/drawer，390–420 无整页横向滚动；核心表格采用 priority columns/stacked rows。所有键盘焦点、dialog semantics、tabs semantics、label/error association、contrast 和 reduced motion 必须验证。

## 9. Full-Stack Test Environment 要求

见 [`FRONTEND_V2_TEST_ENV_REQUIREMENTS.md`](FRONTEND_V2_TEST_ENV_REQUIREMENTS.md)。最终证据必须区分 Unit、Component、Browser Integration、Full-Stack Test Environment、Business Validation。真实普通路径必须是：登录 → 新建任务 → 真实 DOCX → seal → 持久 Worker/model → 真实产物 → 详情 → Review → accept/reject → selected 下载；Compare 也要走 React 页面和真实 compare worker。当前交接事实表明 snapshot-19 D01–D20 gate 为 0/20，D06 虽有真实链路但 delivery incomplete，因此不能写成完整交付。

## 10. Testing Gate

- Gate A：基线、parity matrix、已知问题复现、构建和现有测试记录。
- Gate B：P0/P1 correctness、pending/下载/401/CSV/phase regression。
- Gate C：TanStack Query、auth、old cache removal、invalidation/polling。
- Gate D：Tasks/New Task/Task Detail/Document Detail/Review 视觉和交互完成。
- Gate E：Compare React parity、legacy dependency 仅作明确 fallback。
- Gate F：Vitest/RTL/axe、browser、console/network、responsive、visual、performance。
- Gate G：Full-Stack Test Environment 部署后真实 Worker/model/DOCX/Review/artifact/Compare 验收。

## 11. 禁止事项

- 不删除或降低既有上传/恢复/Review/Compare/API 能力。
- 不把 mock、fixture、HTTP 200、页面打开或隔离诊断冒充真实 Worker/model/业务交付。
- 不把 pending 当 accept，不把 working 当 final，不隐藏 unresolved。
- 不在本分支顺带重构 Recall/Generation 引擎；若 API 兼容确有必要，单独记录。
- 不写入或输出任何凭据；不部署生产。
- 不删除用户已有 dirty/untracked evidence。

## 12. Definition of Done

在所有实现和证据完成前，不写 `FRONTEND_V2_STAGING_VERIFIED`。完成条件包括：P0/P1=0；typecheck/lint/build/unit/component/browser/compare 通过；Route/Task/CSV/Status/Reason/401 正确；Review pending-first、draft、security、keyboard、responsive 通过；Compare React parity 与安全 fallback 完成；Full-Stack Test Environment 的真实 DOCX、Worker、model、artifact hash、Review selected flow、Compare flow 和 independent acceptance 均有可追溯证据。真实模型预算或后端环境阻塞保持 `BLOCKED`，不以测试替代。
