# FundLex 多 agent 项目全面检查（2026-10-26）

本报告检查起点为分支 `refactor/backend-engine-finalization`、HEAD `c46d6e8`，工作区初始干净。用户授权多 agent 全面检查；本轮审查阶段不修改应用代码、不部署、不创建真实模型任务。主 agent 统一交叉验证、合并集中问题记录。本报告末尾补录审查完成后的局部修复和验证，不把原始审查结果改写为全项目通过。

## 检查范围与证据边界

五个只读审查 agent 分别检查后端/API/队列、V1/V2 前端、修订引擎与 DOCX、安全/部署/数据、测试与交付证据；主 agent 检查环境、仓库、依赖、文档一致性并执行回归。

- 主机名、内网地址和云实例元数据与 `AGENTS.md` 一致；当前工作机即部署云服务器。公网出口探测本次返回 IPv6，不将其当作服务器更换证据。
- 生产 API/Worker、隔离测试 API/Worker/Compare Worker 均 active；生产 API `127.0.0.1:8010`、测试 API `127.0.0.1:8110`，公网 HTTPS capabilities 为 200。
- 最新历史生产 V1 普通合同证据为 `/tmp/opencode/fundlex-production-v1-e2e-20261026/e2e-v1-o9rfdisxoj2o/`：31/31 targets、19 edits、Claim Replay 通过、final/redline 和 selected 文件下载及 DOCX 检查通过（FL-D276）。本轮只复核既有证据，不声称重新执行真实交付。
- 同批 Compare 有 1113 处差异，coverage=incomplete，包含 header/footer/AlternateContent/drawing/pict 未支持警告（FL-D276）。
- D01–D20 同一冻结版本 gate、8 份 holdout、G06 授权、评测预算和部分 MySQL/飞书验收仍按 FL-D240–FL-D243、FL-D268 保留未决状态。

## 本轮实际检查

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 后端定向 API/store/guide/auth/DB/recovery 回归 | 74 passed / 1 既有 warning | 本轮工具输出 |
| 前端 TypeScript / ESLint | 通过 | `npm run typecheck`、`npm run lint` |
| 前端 Vitest | 锁定 4.1.12，5 files / 14 passed | `npm ci --ignore-scripts` 后 `npm run test -- --run` |
| npm 完整依赖审计 | 历史审查为 6 项；升级后当前为 0 vulnerabilities | `/tmp/opencode/fundlex-audit-20261026-npm.json`、`/tmp/opencode/fundlex-npm-audit-20261026-final.json` |
| npm 生产依赖审计 | 无漏洞 | `/tmp/opencode/fundlex-audit-20261026-npm-production.json` |
| README / AGENTS / docs 顶层本地文档链接 | 缺失目标 0 | 本轮链接扫描 |
| 完整 Python 回归 | 当前 clean HEAD **1542 passed / 52 skipped / 3 warnings / 358.46 秒** | 本轮 `PYTHONPATH=. .venv/bin/pytest -q`；MySQL/Compare MySQL 真实连接测试因环境变量未配置而跳过 |
| V1/V2 浏览器回归 | 当前 clean HEAD **40 passed** | 本轮 `FUNDLEX_BROWSER_TESTS=1 .venv/bin/pytest -q tests/browser/test_frontend_v2.py tests/browser/test_workbench.py` |

完整回归已结束；各方向代码发现及集中记录编号见下文和 `docs/DETAIL_ISSUES_AND_RESOLUTIONS.md`。本报告不是完成开发或 GO 声明。

## 已确认的维护问题

1. 历史审查时 `frontend/package.json` 固定使用 Vitest 2.1.9，其依赖中含旧版嵌套 Vite/esbuild、tinypool、mocker 等审计告警。随后已升级并用 `npm ci --ignore-scripts` 重建，当前 package/lock 声明和实际执行器均为 Vitest 4.1.12；typecheck、lint、5 个测试文件/14 项测试、build 和当前 `npm audit` 均通过。历史审计输出仍保留，不能把依赖升级扩大为项目级交付通过。
2. README 仍主要描述 2026-10-14 的 v1/v2 固定 action 时代；实施计划 P1–P8 勾选未同步后续实现；ACTIVE_HANDOFF 顶部已记录最新普通交付，但后续历史段落仍有 dirty/旧 HEAD 等时态。建议保留历史并增加唯一当前状态索引，区分生产部署、候选版本、真实质量 gate。文档已归档不等于状态说明已收敛。
3. 仓库没有 `.github` CI 配置；`recall.py` 8042 行、`recall_pipeline.py` 4904 行，`process_recall_first()` 1522 行，Claim Replay 主函数 800 行。以上是维护风险与自动回归入口缺口，不能单凭体积判定运行错误。建议后续按稳定契约拆分，并先保持现有安全门禁与真实业务回归。

4. V1 浏览器套件本轮 36/37 通过，唯一失败是普通 member 进入 `#settings` 后测试仍要求整个设置页隐藏；当前设计允许普通用户使用飞书绑定/运行能力设置，管理员专属操作仍在 `/api/admin/*` 后端门禁内。该测试契约漂移已登记为 FL-D279，不能直接作为越权缺陷或把它静默忽略为全绿。

## 各方向审查结论

### 后端、API、Worker 和持久化

- 已核对任务创建时绑定 `recall_first`、指引版本和规则 hash；普通交付的 final/redline 与 working artifact 门禁、下载时校验、owner 查询和顺序旧 token 拒绝路径存在。
- 新增 FL-D289：普通文档 `RunStore.finish()`、`retry()` 以及最大尝试过期清理的最终更新没有绑定 fencing token 等条件，代码时序上存在旧 Worker 覆盖新 Worker 的风险。该问题是审查推演，未在真实 MySQL 并发中复现。
- 新增 FL-D290：指引解析 job 没有 fencing token，旧解析 Worker 的 release/finish 可能覆盖新尝试的状态或 rules JSON；现有测试是顺序覆盖。
- 新增 FL-D291：并发修订选择分步发布 `selected_final`/`selected_redline`，可能形成不同选择的混合产物；新增 FL-D292：损坏 `report_json` 可使报告或任务列表路径抛出 500。
- 任务失败计入 completed 的遗留口径已由后端 agent 关联 FL-D123；前端 V2 failed 筛选的实际用户影响另记 FL-D294。

### V1/V2 前端和用户流程

- TypeScript、ESLint、Vitest 4.1.12 通过；V1/V2 浏览器回归当前 clean HEAD 为 40 passed。历史 36/37 失败是 FL-D279 的设置页角色测试契约漂移，已由测试契约修正并回归验证，不能直接定性为越权。
- FL-D293：Compare 首次上传封存成功后，`continueUpload()` 仍调用旧闭包的 `task.refetch()`，可能把成功操作误报为上传中断。
- FL-D294：V2 提供 failed 筛选，但后端通常把含失败合同的全终态任务聚合为 completed，筛选和任务状态契约不一致。
- FL-D295：V2 的 API 和静态资源根路径未覆盖 URL 前缀部署；当前 `/test/` 证据只验证 V1，V2 前缀链路仍未验收。
- 已有 FL-D244/245/251/264 等状态边界、异步窗口与前缀隔离事项仍按原记录保留，静态检查通过不等于真实 Worker/DOCX 交付已验证。

### 修订引擎和 DOCX

- 本轮沿用已有 FL-D032、FL-D045–FL-D047、FL-D063–FL-D065、FL-D079–FL-D080、FL-D100–FL-D120、FL-D157–FL-D166、FL-D204–FL-D228、FL-D270、FL-D275 等记录的真实缺陷、修复和未决边界。
- FL-D263 的修订引擎复核发现其 sibling policy 修复不完整：用内置 G18 `INDEPENDENT` operation 加无关 synthetic G100 sibling 的离线夹具可得到 `replay_claims verified=true`、G18 `ALREADY_SATISFIED`、无 open obligation 和 delivery complete。该复现证明确定性证明链存在错误关闭路径，但尚未证明真实生产合同已经通过该路径绕过。
- 既有生产 V1 普通合同证据证明一份普通公开合同完成了 31/31 targets、19 edits、Claim Replay、Review 选择版和 DOCX 下载校验；它不能外推为 20 份开发集、8 份 holdout 或 Compare 全结构覆盖通过。
- Compare 已有真实任务和 1113 处差异，但 coverage 仍为 incomplete，header/footer、AlternateContent、drawing、pict 等可见结构缺口保持 FL-D276 的 NO-GO 结论。

### 安全、部署和数据

- 未发现明确的认证绕过、跨用户资源读取、对象路径穿越或下载授权绕过；现有密码认证、session hash、owner 查询、对象路径校验、交付门禁和 DOCX ZIP 限制已核对。
- FL-D283–FL-D288 已记录实际全 root sudo 与“受限发布”文档漂移、生产 systemd 沙箱缺失、测试/生产复用 LLM 凭据、Database repr/异常泄露、发布器漏重启 Compare Worker，以及上传请求级资源门禁缺口。
- 这些条目均是只读配置/源码审查；本轮没有修改 sudoers、systemd、Nginx、环境变量或服务，也没有打印凭据值。

### 测试、评测和交付证据

- 完整 Python 回归：1497 passed、48 skipped、2 warnings；跳过项包含未配置真实 MySQL/Compare MySQL 测试，因此不能替代 MySQL 并发、恢复和 outbox 验收。
- 前端 typecheck/lint 通过，Vitest 4.1.12 为 5 files / 14 passed；浏览器套件当前为 40 passed。
- npm 完整审计历史结果为 6 项开发依赖漏洞（2 critical、1 high、3 moderate），依赖升级后当前审计为 0 vulnerabilities；FL-D277 已更新为“升级已实施、仍需在最终候选复核”的状态。
- 仓库无 `.github` CI 配置；大文件和关键流程的维护风险、测试入口与文档漂移已在 FL-D278 及既有条目中记录。
- 集中问题记录的编号唯一性校验仍失败：FL-D088、FL-D089、FL-D118、FL-D152、FL-D153、FL-D224 各有两个不同含义的一级标题。FL-D077 原先记录的“已实施并验证”结论已在本轮降级为“历史修复不完整”，本轮没有擅自重排历史编号；该文档治理缺口继续阻止把集中记录当作无歧义的唯一索引。
- 测试与交付审查补充：`tools/deploy/cloud_verify.py` 只覆盖临时账号、测试 DOCX、上传和 seal，未覆盖真实 Worker/model/DOCX 交付、Review、selected artifact、下载和哈希核验，已登记 FL-D296。`rules/rules_v2.json` 的 `unreleased`/`auto_write_enabled=false` 与 README 的“22 action 已发布、自动写入可用”直接冲突，已登记 FL-D297，并与 FL-D278 的文档漂移关联。
- 修订引擎/DOCX 复核补充：选择接口对未知或偶数修订 ID 缺少输入校验，离线复现显示 HTTP 200 的响应可能与实际 `selected_final` 文本不一致，已登记 FL-D298。现有选择及集成定向回归通过不能覆盖无效客户端决策场景。

## 最终判断

项目当前保持 **NO-GO（项目级完整交付未通过）**。已验证的范围是：一份生产 V1 普通公开合同沿真实工作台路径完成交付，以及一批本地/隔离环境的 API、前端和文档回归。未完成或未通过的项目级门禁包括：D01–D20 固定分母 gate 当前为 0/20、8 份 holdout、G06 语义授权、Compare 可见结构完整覆盖、真实 MySQL 并发/恢复、飞书生产网络链路，以及完整交付所要求的持续评测与预算闭环。

补录（2026-10-26）：审查后已提交 `0466712`（稳定 API 错误码/报告边界）和 `cdf0699`（任务状态契约与 V1/V2/Feishu UI），并在工作区继续完成 Feishu OAuth/store、入口和浏览器回归整合。锁文件重建后 Vitest 实际为 4.1.12，14 项通过；后端定向 59 项通过（1 warning），浏览器 40 项通过。原始审查结论、项目级 NO-GO 和真实交付边界保持不变；OAuth 真实扫码回调、MySQL 并发、Compare 完整结构、固定评测 gate 和完整 D01–D20 交付仍未完成。FL-D299 记录原 FL-D294 编号冲突后的任务状态条目更正。
