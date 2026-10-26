# V1 三业务工作台实施与验收进度

## 授权与边界

- 2026-10-27 用户授权按上一轮方案自主多阶段实现、测试、推送、部署与真实端到端交付；不再等待中间审批。
- 仅 V1；三个并列业务：合同修改（主业务）、合同比对、指引生成。候选发布不自动启用运行时修改指引。
- 分支 `codex/v1-three-business-workspace`，起点 `c9b3693`。`9f21349` 保存方案，`87601d3` 保留生产 api.py 修复基线。
- 不动 `/home/opencode/fundlex` dirty 内容；从中仅选择所需生成模块并核对依赖。禁止整仓同步生产，保留既有引擎/Feishu/selection 修复。

## 阶段门禁

| 阶段 | 内容 | 当前状态 | 验收依据 |
|---|---|---|---|
| P0 | 方案落盘、生产基线、分工、风险和费用登记 | 已完成基线，真实费用待启动前登记 | 本文、AGENTS、原方案、基线提交 |
| P1 | V1 侧栏、路由/深链、业务子页 | 已实现，本地回归通过 | 三业务平级；旧链接兼容；返回/刷新/身份隔离 |
| P2 | 合同修改列表/新建/详情/单合同结果 | 已实现，本地回归通过 | 单合同独立页、审阅草稿、返回和选择生成保持；真实路径待验收 |
| P3 | 比对列表/新建/阅读器、指引生成工作区 | 进行中 | 比对右栏不回退；生成5个业务标签/版本门禁 |
| P4 | 全类型工作台与可靠后端聚合 | 进行中 | owner隔离、全量搜索/分页/任务统计、不混单位 |
| P5 | 自动化回归、截图与候选版本冻结 | 待执行 | 390/768/1440；API/浏览器；无V2修改 |
| P6 | 白名单部署、三条真实路径、产物复核、清理 | 待执行 | 真Worker/模型、DOCX/报告/鉴权；无障碍物冒称完成 |
| P7 | 集中记录/交接/提交推送/最终结论 | 待执行 | 问题均入册，产物与部署版本可追溯 |

## 并行分工（共享当前工作树，不并行提交）

- 主agent：frontend/{app.js,app.css,compare.html,compare.js,compare.css}、总集成、集中记录、部署与验收。
- 后端agent `ses_e86a2d974ffe3S3l2AzBY1XB3o`：fundlex/api.py、workspace.py、guide_generation/、regulatory/、必要依赖和后端测试；不部署、不调用模型。
- 生成前端agent `ses_e86a26862ffepc56ZAWz9hM01b`：frontend/guide_generation.{js,css}、独立生成页浏览器测试；不动共享壳/后端。
- 主agent统一合并问题编号和提交，子agent不改集中记录。

## 共享接口约定

- `/api/workspace/tasks`：kind revision/compare/generation，可靠 owner-wide stats + 搜索/状态/日期/排序/分页；每项含id/kind/name/status/phase/time/scale/attention。
- `window.FundLexWorkbench.navigate(view,{mode,id,tab,...})`、`json`、`download`、`epoch`、`authenticated` 共享；`fundlex:route` 事件传 view/mode/id/tab；生成页挂载 #gg-root；身份reset清理。
- V1 hash承载模式与对象id；当前任务/单合同是业务子页面，不作为全局侧栏项。

## 真实运行与费用

- 本轮尚未发起真实模型调用。Compare确定性任务无需模型。
- 后端agent先查既有共享预算/实际模型可用性与公开法规样本；主agent在启动真实调用前登记本轮限额、账本和任务，禁止并行无限重试/覆盖全语料消耗。
- 目前磁盘约947MB可用，禁止复制生产整树；备份仅白名单文件。外网IPv4查询返回IPv6出口，但 hostname/网卡/instance-id 已事实确认同一生产机。

## 当前断点

- 后端与生成前端已并行启动，主agent开始V1导航/路由/首页/修改与比对子页面；未部署。

### 2026-10-27 第一轮集成结果

- `bf3f855` 补齐与生产 API 配套的 selective/store/api_errors/Feishu OAuth/store 原版：当前分支旧 API 搭配不了生产新 manifest/report/OAuth 契约；仅保存生产已部署版本，不向生产回退这些文件。
- V1 已实现：工作台三入口与跨业务列表、侧栏重组、hash对象深链、修改列表/新建/任务详情/独立合同结果与审阅、比对三模式拆分及右侧差异栏、修改指引页与飞书绑定保留。
- 主线浏览器 `tests/browser/test_compare_selection_v1.py tests/browser/test_workbench.py tests/browser/test_workspace_v1.py` **46 passed / 106.96s**。已修复真实缺陷：后台 refresh 反复重建独立合同页，导致“生成选择版”控件被刷新替换；现在仅首次就绪/缺少详情时水合。原夹具补齐新增单合同 GET，旧“侧栏新建/详情”断言改为业务内页面导航。
- 后端首轮生成/聚合 **44 passed**，旧API定向 **40 passed/9 skipped**；生成UI首轮 **15 passed**。后端agent正在补 real ModelGateway 指引任务注册、候选状态/分页；生成UIagent补真实分页与显式重试按钮。两者同session继续，无额外agent。
- 剩余：新修改尚未全量冻结；单worker部署、corpus ACL、环境备份、模型预算登记与真实调用/三条生产路径未执行。旧生产仍完整运行，尚未发布本次代码。
