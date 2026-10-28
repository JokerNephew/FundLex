# 全面整改执行进度

更新2026-10-28。用户已授权实际开发与端到端交付，阶段方案见`COMPREHENSIVE_REMEDIATION_EXECUTION_PLAN_20261028.md`。无费用/调用次数审批，账本只观测。

| 阶段 | 状态 | 验证/提交/剩余 |
|---|---|---|
| S0 基线/ownership | 已完成基线 | 分支`codex/comprehensive-remediation-20261028`，基线提交`9e85f91`；五个隔离worktree已建。不将审查提交误作业务修复 |
| S1 安全/无cap/资格 | 开发中 | 运行策略/评分D、法规生成C、发布/依赖E并行；预检有阻塞须先报主agent |
| S2 业务完整性/证明 | 开发中 | A引擎；生产价值优选摘要假complete必须复验 |
| S3 DOCX/Compare | 开发中 | B |
| S4 多渠道/前端恢复 | 部分待分派 | C/D/E；飞书/任务与前端下一波，避免共享文件冲突 |
| S5 发布/运维恢复 | 开发中 | E处理候选发布器/workspace/依赖；主agent部署阶段执行root侧 |
| S6 真实评测优化 | 待开工 | 先独立标签/评分器；20–30份实际DOCX与回归 |
| S7 部署/正式用户E2E | 待开工 | 非离线替身；产物独立复核及授权下载 |

当前整体NO-GO，尚无本轮工程修复完成声明；只有测试、独立业务复核和真实E2E通过后才更新。独立worktree：
`/tmp/opencode/fundlex-remediation-{engine,docx-compare,guide-runner,runtime-scorer,ops-release}`；分支名`codex/remediation-*`。

原审查证据保留`/tmp/opencode/comprehensive-audit-20261028/`，新执行证据`/tmp/opencode/comprehensive-remediation-20261028/`，prestart patch已保存。原合同/gold/历史manifest和两个备份目录不动。开发agent开工问题先交主agent内部澄清，开工后自主开发测试，不向用户反复提问。

主agent当前：审阅候选接口/生产分叉、准备S6独立标签盲读和S7验收脚本；未部署/重启，不重复agent负责代码。首批selection已在`adcb416`冻结（20dev/8holdout，含保护边界BH06；5个旧.doc排除并记录）。S7脚本`tools/evaluation/production_first_batch_e2e_20261028.py`已加入（`be978a7`），待发布后执行正式工作台+产物+选择版+未授权检查。
MySQL独立实例已在本机3308临时数据目录启动（非生产库），`tests/test_db_mysql.py` **6 passed**，可作为后续并发/迁移验证；凭据仅运行时环境，不写入仓库或文档。不得把该测试指向生产`fundlex`库。
