# Semantic V2 与端到端交付计划（2026-10-29）

## 目标
用“指引语义 + 模型理解 + 代码证明”替换合同特定措辞变体，完成开发、回归、holdout、生产部署与真实 E2E；失败样本保留。

## 版本与基线
- 分支：`codex/comprehensive-remediation-20261028`
- Semantic V2 Phase 1：`3b56ff5`，模型 ID 归一化 `740c35e`
- 第一波基线：`5c0aa71`（20 dev：15 业务通过 / 5 失败；标签 304/390）
- 默认开关：`FUNDLEX_SEMANTIC_V2=0`；实验：`1` + `FUNDLEX_SEMANTIC_V2_RULES=...`
- 标签：`semantic-v2-phase1`（Phase 1 完成）、后续每阶段一个 tag

## 阶段与门禁

### P0 冻结基线
- 保存 20 dev 通过/失败与证据。
- 全量非浏览器回归：**2158 passed / 6 skipped / 760.67s**。
- 门禁：无未提交的本轮代码；不覆盖并行 Compare 改动。

### P1 Semantic V2 基础（已完成）
- `fundlex/semantic_contract.py`：SemanticTarget / SemanticPolicy / 通用校验。
- `guides/semantic_policies_v1.json`：G02/G03/G04/G05/G09/G16/G18/G22。
- 模型任务 `recall_semantic_target`。
- 规划器 `semantic_v2` 分支；flag 默认关闭。
- 单测 4 + pipeline 58 通过。

### P2 垂直切片（进行中）
- 先用 G09/G16/G22 跑 B15/B12；G02/G04/G09/G16/G22 跑 B05/B19。
- 检查 `semantic_v2.accepted/rejected`、最终 edits、Claim Replay、独立复核。
- 门禁：至少 B15 G09、B12 G16 的实际最终内容正确；Semantic target 未被通用校验误拒。

### P3 扩展到 G02/G04/G05/G18
- 逐条把合同特定分支改为 semantic selector；旧分支保留 shadow。
- 门禁：20 dev 中新旧路径对比不退化；失败样本不增加；模型调用可接受。

### P4 20 dev 影子/正式评估
- 同批 20 份跑旧路径与 Semantic V2，记录：完成数、业务复核、false complete、模型调用、耗时、失败类型。
- 门禁：业务通过 ≥ 基线 15/20；不得出现 false complete；失败样本保留。

### P5 8 份 holdout
- 冻结版本/标签/指标后运行；不得针对 holdout 调参。
- 门禁：holdout 业务通过率达到预设门槛（先记录基线，不以单份外推）。

### P6 生产部署与真实 E2E
- 最新候选从干净 worktree 发布；五服务 active、workspace 401、capabilities 200。
- 正式工作台：注册/登录/当前指引/上传真实合同/真实模型/结果页/下载 final+redline+报告。
- 独立业务复核 + 机械 10 项；失败则回滚。
- 门禁：单合同真实 E2E 通过，不等于整批/全量通过。

### P7 扩样
- 100 → 250 → 514+；每波冻结标签/来源/指引/引擎版本/指标/分母；失败、受保护、不可解析样本单列。
- 门禁：按执行计划分层，不隐去失败分母，不按样本特判。

## 版本管理
- 每次代码变更：定向测试 → 提交 → 更新 ACTIVE_HANDOFF。
- 每个阶段：tag（`semantic-v2-p1`, `p2`, ...）。
- 生产候选：干净 worktree + publish script；保留/回滚。
- 不把并行 Compare 改动混入本分支提交。

## 风险与回退
- 模型返回 schema 不稳定 → 通用校验拒绝，保留 rejected 证据，不自动用旧正则补。
- Semantic V2 导致回归 → flag 关闭，旧分支回退。
- 生产失败 → 发布器自动回滚；保留日志/备份。
- 磁盘/Worker reserve：发布前后检查。
