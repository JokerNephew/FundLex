# 全面整改执行进度

更新2026-10-28。用户已授权实际开发与端到端交付，阶段方案见`COMPREHENSIVE_REMEDIATION_EXECUTION_PLAN_20261028.md`。无费用/调用次数审批，账本只观测。

| 阶段 | 状态 | 验证/提交/剩余 |
|---|---|---|
| S0 基线/ownership | 已合并，回归通过 | 分支`codex/comprehensive-remediation-20261028`；基线`9e85f91`，A–H及标签分支已合并；非浏览器（含隔离MySQL）**2106 passed/6 skipped/679.14s**，浏览器**69 passed/224.11s**。不将合并/单测误作业务修复 |
| S1 安全/无cap/资格 | 已实施，待生产/真实模型 | D/C/E：cap纯观测、config/资格/不可变/fencing/下载核验/依赖/上传/sandbox代码与回归已合并；生产env/root发布/权限仍待执行 |
| S2 业务完整性/证明 | 已实施，单合同真实验证通过 | A：批准绑定、site proof、坐标、分页、摘要目标、统一门禁；value first7 21/21标签完成且独立复核通过（P2空白段），其余28/514待跑 |
| S3 DOCX/Compare | 已实施，待Word/真实任务 | B：叠加/Review/坐标/Compare边界；合成及弘利临时副本+相关测试通过，Word/WPS未验 |
| S4 多渠道/前端恢复 | 已实施，待真实渠道 | G/H/C：任务/飞书/前端/法规恢复代码及隔离测试通过；真实飞书/生产workspace/浏览器生产E2E待验 |
| S5 发布/运维恢复 | 代码已准备，未部署 | E：workspace/五服务发布器/依赖/备份工具/sandbox模板；root `/usr/local/sbin`、生产env、备份恢复待主agent受控执行 |
| S6 真实评测优化 | 首波标签v2完成，单合同通过 | 28→约100→约250→funds_word根514+首批28（unique约542）；v2 501 targets/51 unresolved findings单列；B02真实first7 21/21+独立复核通过，其余20dev/8holdout待跑 |
| S7 部署/正式用户E2E | 待开工 | 非离线替身；生产env/发布、真实合同、产物独立复核及授权下载 |

当前整体NO-GO，尚无本轮工程修复完成声明；只有测试、独立业务复核和真实E2E通过后才更新。独立worktree：
`/tmp/opencode/fundlex-remediation-{engine,docx-compare,guide-runner,runtime-scorer,ops-release}`；分支名`codex/remediation-*`。

原审查证据保留`/tmp/opencode/comprehensive-audit-20261028/`，新执行证据`/tmp/opencode/comprehensive-remediation-20261028/`，prestart patch已保存。原合同/gold/历史manifest和两个备份目录不动。开发agent开工问题先交主agent内部澄清，开工后自主开发测试，不向用户反复提问。

主agent当前：已把A–H及v2标签合并；`p6_score`适配新标签schema并增加段落hash到全XML坐标的映射（`a4d2b46`）。首批v2标签501 targets/51未解决findings单列。真实value first4曾因正文G16重复（p799/p802）被独立复核拒绝（33 targets/17 edits/25 calls/621s/$0.0844），已登记FL-D481并加入append物理clause站点归一去重。first7 `complete`，29 targets/16 edits/28 calls/527s/$0.0742341，摘要p1258与正文G16各1份，v2标签21/21 completed、false_complete=0，独立复核通过（仅P2 p800/p801空段）；证据`docs/evidence/value-first7-*`。first/first2/first3/first6分别因mode/4k/12k reasoning/API key失败，保留为失败证据，不计入通过。
S7脚本`tools/evaluation/production_first_batch_e2e_20261028.py`已加入（`be978a7`），待正式候选部署后执行浏览器+授权下载+选择版。
MySQL独立实例已在本机3308临时数据目录启动（非生产库），`tests/test_db_mysql.py` **6 passed**，可作为后续并发/迁移验证；凭据仅运行时环境，不写入仓库或文档。不得把该测试指向生产`fundlex`库。生产env/root publisher/DB+对象备份仍未动。
