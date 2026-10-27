# V1 三业务工作台实施与验收进度

## 授权与边界

- 2026-10-27 用户授权按上一轮方案自主多阶段实现、测试、推送、部署与真实端到端交付；不再等待中间审批。
- 仅 V1；三个并列业务：合同修改（主业务）、合同比对、指引生成。候选发布不自动启用运行时修改指引。
- 分支 `codex/v1-three-business-workspace`，起点 `c9b3693`。`9f21349` 保存方案，`87601d3` 保留生产 api.py 修复基线。
- 不动 `/home/opencode/fundlex` dirty 内容；从中仅选择所需生成模块并核对依赖。禁止整仓同步生产，保留既有引擎/Feishu/selection 修复。

## 阶段门禁

| 阶段 | 内容 | 当前状态 | 验收依据 |
|---|---|---|---|
| P0 | 方案落盘、生产基线、分工、风险和费用登记 | 已完成 | 本文、AGENTS、原方案、基线提交及费用前后快照 |
| P1 | V1 侧栏、路由/深链、业务子页 | 已发布并验证 | 三业务平级；旧链接兼容；返回/刷新/身份隔离 |
| P2 | 合同修改列表/新建/详情/单合同结果 | 已发布，UI回归通过 | 单合同独立页、审阅草稿、返回和选择生成保持；正式修改产物受模型服务阻塞 |
| P3 | 比对列表/新建/阅读器、指引生成工作区 | 已开发、已发布 | 比对真实产物通过；生成5标签/版本/重试门禁测试通过，模型输出受402阻塞 |
| P4 | 全类型工作台与可靠后端聚合 | 已发布并验证 | owner隔离、全量搜索/分页/任务统计、不混单位 |
| P5 | 自动化回归、截图与候选版本冻结 | 已完成 | 373passed；4尺寸；无V2修改 |
| P6 | 白名单部署、三条真实路径、产物复核、清理 | 部分通过，外部HTTP402阻塞 | 比对通过；修改/有效候选未通过，暂停护栏通过；6账号已清理 |
| P7 | 集中记录/交接/提交推送/最终结论 | 已完成 | origin分支已推送并核对；FL-D349–354、部署清单与证据齐全；P6阻塞及整体NO-GO保留 |

## 当前最终边界（优先于下方开发过程记录）

- P0–P5 已开发并验证；P6 已发布并通过页面smoke/真实比对，但合同修改与有效候选生成受HTTP402阻塞；**P6未全部完成，整体不能标GO**。用户要求的V1三业务UI已上线，不是三条模型交付均成功。
- 组合回归 **373 passed / 30 skipped / 1 deselected(V2) / 1 warning / 236.71s**；后续清理安全新增回归4passed。此前组合出现过一次Playwright disposed与固定100ms等待夹具竞争，后者改为等待实际pending，最终上述组合通过。
- 主源码提交：09228b6（V1架构）、82d7817（生成/聚合）、1b525b8（MySQL建表/发布工具）、189e460（MySQL upsert）、13fb31d（模型失败暂停，不产空候选）。最新文档提交以git为准。
- 部署：39文件白名单，激活前每个文件与git内容SHA一致。基线API及五个安全companion来自生产，未覆盖其他工作树dirty引擎代码。备份 `/tmp/opencode/v1-three-business-release-20261027-mysqlfix`，后续两个小修分别留before文件与patch manifest；新单实例生成Worker已启用。
- 环境：新增PyMuPDF1.28.2、公开corpus最小ACL、两个非秘密配置键；原env完整root0600备份。原修订Worker领取队列曾自动重启3次，确认无执行lease后暂调为单DBconsumer，根因未冒称解决（FL-D354）。
- 线上验证：工作台与7项静态资源200/SHA一致，版本3a279b194c8ef97d；侧栏为工作台/合同修改/合同比对/指引生成/修改指引/飞书绑定/管理员用户管理。1440/1280/768/390无横向溢出，深链/返回/刷新通过。
- 真实比对已交付：账号e2e-v1ws-321153671c3cc222，普通登录→公开合同上传→生产Compare Worker→选择/刷新→生成→4项下载、哈希、实际DOCX修改/修订检查通过。合同比对无需模型。
- 真实修改和生成失败保留分母：正常修改paused；两次生成暴露MySQL兼容和外部HTTP402，修复后另一次生成已证实正确暂停。空候选没有算通过；本人未重置gate、未换模型、未启用候选。详见FL-D352/353。
- 费用只增4个真实HTTP/$0.02739885，ledger原费用未重置；停止模型尝试。所有6个临时账号已dryrun→清理→二次查无残留，包含3个生成任务/1修改任务/1比对任务；公共语料索引/快照明确保留，不删共享数据。
- 证据根 `/tmp/opencode/v1-three-business-20261027/`，各阶段result.json/cleanup.json、budget-before/after、公网static检查和截图均可追溯。真实非空生成/正式修改产物验收剩余阻塞待模型额度恢复后继续。
- 10:14 CST最终复核：39文件与13fb31d逐字节匹配，最终发布清单 `...-mysqlfix/final-manifest.json` 保留初始SHA与后续两次补丁记录。公网7资源再次匹配；四服务active/running。修改Worker单consumer后的约6分钟空闲观察无新数据库错误，非带载/并发回归；历史3次自动重启保留。
- 收尾定向回归：清理/模型暂停/MySQL兼容合计7passed（0.89s）；账本仍30270，无新增付费调用。
- 版本管理：`codex/v1-three-business-workspace` 已推送origin，8778656已通过远端ls-remote核对；最终文档提交以git HEAD为准。没有合并或覆盖其他工作树，也没有将P7完成写成P6全部通过。

## 并行分工（历史；均已结束，不并行提交）

- 主agent：frontend/{app.js,app.css,compare.html,compare.js,compare.css}、总集成、集中记录、部署与验收。
- 后端agent `ses_e86a2d974ffe3S3l2AzBY1XB3o`：fundlex/api.py、workspace.py、guide_generation/、regulatory/、必要依赖和后端测试；不部署、不调用模型。
- 生成前端agent `ses_e86a26862ffepc56ZAWz9hM01b`：frontend/guide_generation.{js,css}、独立生成页浏览器测试；不动共享壳/后端。
- 主agent统一合并问题编号和提交，子agent不改集中记录。

## 共享接口约定

- `/api/workspace/tasks`：kind revision/compare/generation，可靠 owner-wide stats + 搜索/状态/日期/排序/分页；每项含id/kind/name/status/phase/time/scale/attention。
- `window.FundLexWorkbench.navigate(view,{mode,id,tab,...})`、`json`、`download`、`epoch`、`authenticated` 共享；`fundlex:route` 事件传 view/mode/id/tab；生成页挂载 #gg-root；身份reset清理。
- V1 hash承载模式与对象id；当前任务/单合同是业务子页面，不作为全局侧栏项。

## 开发初期真实运行与费用（历史；以顶部及预算结算为准）

- 本轮尚未发起真实模型调用。Compare确定性任务无需模型。
- 后端agent先查既有共享预算/实际模型可用性与公开法规样本；主agent在启动真实调用前登记本轮限额、账本和任务，禁止并行无限重试/覆盖全语料消耗。
- 目前磁盘约947MB可用，禁止复制生产整树；备份仅白名单文件。外网IPv4查询返回IPv6出口，但 hostname/网卡/instance-id 已事实确认同一生产机。

## 开发初期断点（历史；以顶部最终边界为准）

- 后端与生成前端已并行启动，主agent开始V1导航/路由/首页/修改与比对子页面；未部署。

### 2026-10-27 第一轮集成结果

- `bf3f855` 补齐与生产 API 配套的 selective/store/api_errors/Feishu OAuth/store 原版：当前分支旧 API 搭配不了生产新 manifest/report/OAuth 契约；仅保存生产已部署版本，不向生产回退这些文件。
- V1 已实现：工作台三入口与跨业务列表、侧栏重组、hash对象深链、修改列表/新建/任务详情/独立合同结果与审阅、比对三模式拆分及右侧差异栏、修改指引页与飞书绑定保留。
- 主线浏览器 `tests/browser/test_compare_selection_v1.py tests/browser/test_workbench.py tests/browser/test_workspace_v1.py` **46 passed / 106.96s**。已修复真实缺陷：后台 refresh 反复重建独立合同页，导致“生成选择版”控件被刷新替换；现在仅首次就绪/缺少详情时水合。原夹具补齐新增单合同 GET，旧“侧栏新建/详情”断言改为业务内页面导航。
- 后端首轮生成/聚合 **44 passed**，旧API定向 **40 passed/9 skipped**；生成UI首轮 **15 passed**。后端agent正在补 real ModelGateway 指引任务注册、候选状态/分页；生成UIagent补真实分页与显式重试按钮。两者同session继续，无额外agent。
- 剩余：新修改尚未全量冻结；单worker部署、corpus ACL、环境备份、模型预算登记与真实调用/三条生产路径未执行。旧生产仍完整运行，尚未发布本次代码。
