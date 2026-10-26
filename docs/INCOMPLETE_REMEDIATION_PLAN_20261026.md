# FundLex `incomplete` 修复与真实交付计划

日期：2026-10-26

## 目标

降低真实合同的 `succeeded/incomplete` 比例，同时保持安全交付门禁。目标不是把状态字段改成 `complete`，而是让实际 DOCX 对每个适用义务完成：

`原件定位 → 事实与适用性 → 目标盘点 → 联合计划 → DOCX 写入 → 独立复核 → Claim Replay → 授权下载`。

只有实际文件、报告、修订等价、哈希和业务门禁全部一致时才允许 `complete`。无法安全完成的合同继续输出明确的工作文件和未完成清单。

## 当前基线

- 生产 MySQL：666 份合同，335 份 `succeeded/incomplete`（50.3%），246 份 `succeeded/complete`。
- 595 个含合同任务中，318 个至少包含一份 incomplete，307 个全部 incomplete。
- 335 份 incomplete 的首要阻塞：定位/规划/生成 212（63.3%）、独立业务复核 86（25.7%）、Claim Replay 25（7.5%）、其他 12（3.6%）。
- 高频诊断：`RECALL_EDIT_OVERLAP`、`SURVEY_QUOTE_UNRESOLVED`、`RECALL_TARGET_UNRESOLVED`、`RECALL_COMPOSE_FIXED_TEXT_MISSING`、`RECALL_TARGET_COMPOSITE_UNRESOLVED`。
- 现有可用正向证据：D17 真实完整交付；普通 V1 单例真实完整交付。现有失败证据和 D01–D20 分母全部保留。
- 当前工作区存在用户此前未提交修改；不得回退或覆盖。当前生产数据库密码已轮换，值不得进入代码、文档、日志或命令输出。

## 阶段与出口

### P0：冻结基线和隔离变更

交付：本计划、当前 HEAD/dirty 清单、生产统计、错误分母、评测预算账本、独立 worktree。

出口：基线可重复；所有 agent 使用同一源码快照和同一问题编号；没有 agent 直接改集中记录。

### P1：定位与规划修复

范围：目标 overlap、复合目标、跨段边界、duplicate site、quote rebinding、固定文案缺失、operation attribution。

出口：每个根因都有最小可复现夹具；局部回归通过；至少用历史真实报告和保存的原件离线重建验证；不能通过放宽范围或忽略未解决目标。

### P2：Claim Replay 与交付门禁修复

范围：obligation ledger、operation/site 身份、实际 DOCX effect、残留旧文、无授权新增、audit/sweep projection、报告和前端计数一致性。

出口：正例仍可 complete，错误修改仍 fail closed，不能因 sibling 或语义相似文本错误关闭 obligation；Claim Replay 失败原因可定位。

### P3：小批真实合同闭环

先在 qualification 通道用 1–2 份真实合同走当前候选版本和真实模型，保存原件、报告、实际 DOCX、redline、哈希、下载和独立业务复核；规则仍为 `unreleased` 时不得把 qualification 结果写成正式默认交付。候选通过版本证据门禁并正式发布后，再从普通默认入口重跑正式用户验收。每轮修复先局部复测，再决定是否增加真实调用。

出口：真实结果能证明具体根因改善；所有模型调用进入共享账本；失败分母不删除。

正式用户验收至少覆盖：正常应改、长合同、边界/不适用状态、指引切换与恢复、旧任务快照不变；Review 接受/拒绝与 selected 产物；接受后修订等价、拒绝后原文恢复；跨账号下载拒绝；服务重启后任务和产物仍可用。Compare 完整结构、MySQL 并发和真实 OAuth 等既有未闭合项必须逐项取得证据，否则保持 NO-GO。

### P4：20+8 真实评测与优化

按 `docs/EVALUATION_AND_OPTIMIZATION_PLAN.md` 冻结 20 份开发集和 8 份留出集、独立标签、指标、预算和版本 hash。真实读取 DOCX 评分，分别统计目标发现召回、正确完成率、整合同完成率、错误修改、误排、成本和时延。

出口：开发集按根因复测后冻结；只有开发集满足门槛才跑留出；留出失败不得从分母删除。

### P5：候选发布和生产用户验收

整仓一致性发布到隔离测试环境，先执行导入、服务、MySQL、浏览器 smoke；再受控发布生产并备份。正式用户路径必须包含登录、当前指引、真实合同上传、seal、真实 Worker/模型、DOCX、Review、授权下载 final/redline/report、哈希和前后差异。

出口：正常可处理合同至少有真实完整交付；不完整合同明确显示工作文件和例外；服务重启后任务和产物仍可用。

### P6：最终监督和收尾

主 agent 复查所有 agent 的变更、测试证据、问题编号、生产部署 hash、数据库和下载权限；更新集中问题、ACTIVE_HANDOFF、当前状态索引和用户指南。

出口：没有把单测、离线重放、诊断或单例成功冒充完整项目交付；若仍有外部阻塞，明确列出已完成和剩余工作。

## Agent 分工与监督

| Agent | 工作区 | 负责 | 必须提交 |
| --- | --- | --- | --- |
| Engine | 独立 worktree | 定位、规划、复合/跨段、生成失败 | 代码、夹具、定向回归、根因报告 |
| Replay | 独立 worktree | Claim Replay、obligation、delivery gate | 代码、正反例、报告投影回归 |
| Evaluation | 独立 worktree | 生产报告统计、评测工具、错误分母 | 只读分析或评测工具、指标报告，不启动未经登记的模型批次 |
| Delivery | 独立 worktree | 任务状态、下载、Review、前端解释 | 代码、API/浏览器回归、端到端验收清单 |
| Supervisor | 主工作区 | 合并、冲突审查、预算和发布监督 | 合并前审查、阶段 gate、最终真实交付 |

Agent 不得修改 `DETAIL_ISSUES_AND_RESOLUTIONS.md`；主 agent 统一登记发现。任何真实模型调用必须先写入运行目录和共享账本，禁止各 agent 各自重置预算。

## 质量门禁

- 代码门禁：定向测试、全量 Python、前端 typecheck/lint/test/build、compileall、node check、diff check。
- 业务门禁：实际 DOCX 复核；`complete` 必须 Claim Replay true、open obligations=0、blocking unresolved=0。
- 安全门禁：不放宽 fail-closed；不打印密钥/数据库 URL；生产发布整仓依赖一致；发布前备份，发布后 hash 和服务核对。
- 评测门禁：冻结标签后不得按结果改 gold；开发/留出分开；保留失败样本和真实调用成本。
- 交付门禁：普通工作台路径优先；单元测试、替身模型、离线重放和直接调用不能替代最终真实用户端到端。

## 当前执行断点

1. 已完成 P0 的生产统计、问题登记和凭据轮换。
2. 当前开始 P1/P2 并行代码审查和最小夹具设计。
3. 合并后先运行离线/局部回归，再根据预算执行真实小批。
4. 真实评测、发布和最终用户验收必须使用最终冻结版本，不能拼接历史快照。
