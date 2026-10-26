# FundLex 当前状态索引（2026-10-26）

本文件是当前状态的单一入口。它以本次文档治理开始时的代码基线 `c46d6e8570ddf7d472ecf422b486b9c0f21eca79`、当前规则文件和最新生产验收证据为准；历史报告中的“已发布”“complete”或指标，只有在下表明确列为当前证据时才可用于当前结论。

## 当前结论

**整体生产结论：NO-GO。** 普通 V1 已完成一条真实生产用户路径，但 Compare 真实任务的 coverage 为 `incomplete`，且 D01–D20 固定分母 gate 为 **0/20**。G06 授权、完整开发集业务门禁、留出集、正式规则发布和最终普通用户交付门槛仍未闭合。

正式入口是 [`https://fundlex.club`](https://fundlex.club)。[`https://fundlex.club/test/`](https://fundlex.club/test/) 是隔离测试入口，不能作为生产交付入口。

## 版本与规则状态

| 范围 | 当前状态 | 证据与边界 |
| --- | --- | --- |
| 代码基线 | 文档治理前 HEAD 为 `c46d6e8570ddf7d472ecf422b486b9c0f21eca79` | 本索引和本轮文档修改随后以文档 commit 进入 Git；业务源码不在本轮范围 |
| `rules/rules_v1.json` | `release_policy.status = "unreleased"` | 规则文件第 7–12 行；不能据此宣称正式自动写入已开放 |
| `rules/rules_v2.json` | `release_policy.status = "unreleased"` | 规则文件第 10–13 行；`auto_write_enabled = false`，真实运行只属于隔离评测模式 |
| 正式规则发布 | 未满足 | 仍需最终引擎、独立样本、批准记录、发布脚本和运行期指纹门禁的完整证据 |

## 当前生产证据

### 普通 V1

最新普通 V1 真实任务使用登录入口、当前配置指引、DOCX 上传、seal、持久 Worker、真实模型、DOCX 产物、Review accept/reject、selected artifact 下载和报告/哈希核对：

- 任务 `6200b8ad71974c10b613622809fa52f5`，文档 `2adeaefc840b4df68e8be0d060cea16f`。
- 状态为 `completed/succeeded/complete`；31/31 targets completed、unresolved=0、19 edits。
- `artifact_claim_replay.verified=true`；final/redline、报告哈希和 selected_final/selected_redline 下载核对通过。
- Review HTTP 200，19 条修订中拒绝 1 条；证据目录为 `/tmp/opencode/fundlex-production-v1-e2e-20261026/e2e-v1-o9rfdisxoj2o/`，完整路径与边界见 [`ACTIVE_HANDOFF.md`](ACTIVE_HANDOFF.md) 顶部 FL-D276。

这证明普通 V1 的一条当前真实交付链路，不等于规则包已发布，也不等于 20 份开发集或整体项目门禁通过。

### Compare

独立 Compare 真实任务 `191b14f48e264212abe98de5828bcd29` 已创建、完成，reader/view API HTTP 200，发现 1113 处差异；但 coverage 为 **`incomplete`**，含 header/footer、AlternateContent、drawing、pict 未支持警告。Compare 全文交付门禁失败，不能把差异数量或页面可查看性写成完整交付。

### D01–D20 固定分母

当前固定分母 gate 为 **0/20**。D04 最近独立通过证据属于 snapshot-18，D06 最近真实证据属于 snapshot-19 且仍受 G06 语义变体阻断；其他合同分散在更早快照，不能拼接成同一冻结版本的完整 gate。详细对账见 [`evidence/development-gate-reconciliation-20261025/D01-D20-gate-reconciliation.md`](evidence/development-gate-reconciliation-20261025/D01-D20-gate-reconciliation.md) 和 [`REAL_REVISION_EVALUATION_RESULTS.md`](REAL_REVISION_EVALUATION_RESULTS.md)。

## 历史证据边界

- 归档 v2 发布候选、22 action 审计、早期 16 份小批和历史 `complete_with_exceptions` 结果都是历史评测材料；它们不能覆盖当前规则文件的 `unreleased` 状态。
- 历史普通 V1、Compare、离线重建、Replay、机械下载、单元测试和页面 smoke 各自只证明其记录的范围；它们不能替代真实模型调用、实际 DOCX、整合同业务审核或完整用户交付链路。
- `final/redline` 只有在对应真实任务、当前冻结版本、报告、Review 选择和授权下载均能对账时才是该批次的交付证据；`working_final/working_redline` 或 `incomplete` 产物不能冒称最终合同。
- 本轮文档治理仅修改文档和发布状态说明，不修改业务源码、测试代码、规则 JSON、FL-D283 或 FL-D285。

相关入口：[`README.md`](../README.md)、[`ACTIVE_HANDOFF.md`](ACTIVE_HANDOFF.md)、[`REAL_REVISION_EVALUATION_RESULTS.md`](REAL_REVISION_EVALUATION_RESULTS.md)、[`DETAIL_ISSUES_AND_RESOLUTIONS.md`](DETAIL_ISSUES_AND_RESOLUTIONS.md)。
