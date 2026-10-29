# 全面整改执行进度

更新2026-10-28。用户已授权实际开发与端到端交付，阶段方案见`COMPREHENSIVE_REMEDIATION_EXECUTION_PLAN_20261028.md`。无费用/调用次数审批，账本只观测。

| 阶段 | 状态 | 验证/提交/剩余 |
|---|---|---|
| S0 基线/ownership | 已合并，回归通过 | 分支`codex/comprehensive-remediation-20261028`；基线`9e85f91`，A–H及标签分支已合并；非浏览器（含隔离MySQL）**2118 passed/6 skipped/676.41s**，浏览器**69 passed/224.11s**。不将合并/单测误作业务修复 |
| S1 安全/无cap/资格 | 已实施并部署 | D/C/E：cap纯观测、config/资格/不可变/fencing/下载核验/依赖/上传/sandbox代码与回归已合并；生产env新endpoint/无ENFORCE开关、certifi升级、备份权限已执行 |
| S2 业务完整性/证明 | 单合同生产验证通过 | A：批准绑定、site proof、坐标、分页、摘要目标、统一门禁；生产value7 21/21标签、独立复核通过（P2空白段），其余20dev/8holdout/514待跑 |
| S3 DOCX/Compare | 已实施，待Word/真实任务 | B：叠加/Review/坐标/Compare边界；合成及弘利临时副本+相关测试通过，Word/WPS未验 |
| S4 多渠道/前端恢复 | 前端/workspace生产通过，真实飞书待验 | G/H/C：任务/飞书/前端/法规恢复代码及隔离测试通过；生产workspace及浏览器E2E通过；真实飞书消息/回调、法规全类型生产E2E待验 |
| S5 发布/运维恢复 | **已受控部署候选cdf298e** | E：workspace/五服务发布器/依赖/备份工具/sandbox；生产env新endpoint、certifi2026.10.19、DB+对象备份与隔离恢复通过；备份/发布器时间戳bug已修；五服务active、workspace401 |
| S6 真实评测优化 | 首波标签v2完成，单合同生产通过 | 28→约100→约250→funds_word根514+首批28（unique约542）；v2 501 targets/51 unresolved findings单列；B02生产value7 21/21+独立复核通过；其余20dev/8holdout/514待跑 |
| S7 部署/正式用户E2E | **单合同生产E2E通过** | 生产candidate cdf298e，五服务active；浏览器注册/指引/上传/真实模型/结果页/final/redline/报告下载、10项机械检查、21/21标签、独立复核通过；P2空白段 |

当前整体NO-GO，尚无本轮工程修复完成声明；只有测试、独立业务复核和真实E2E通过后才更新。独立worktree：
`/tmp/opencode/fundlex-remediation-{engine,docx-compare,guide-runner,runtime-scorer,ops-release}`；分支名`codex/remediation-*`。

原审查证据保留`/tmp/opencode/comprehensive-audit-20261028/`，新执行证据`/tmp/opencode/comprehensive-remediation-20261028/`，prestart patch已保存。原合同/gold/历史manifest和两个备份目录不动。开发agent开工问题先交主agent内部澄清，开工后自主开发测试，不向用户反复提问。

主agent当前：已完成生产候选cdf298e部署（engine253083…/servicee0625b…），五服务active、workspace未登录401、生产env新endpoint、certifi2026.10.19。生产E2E最终任务6bbb6712…/doc5d35ba80…在651秒内complete；final/redline/报告下载，10项机械检查全过，v2标签B02 21/21，独立业务复核通过（P2 p800/p801空段）。此前生产E2E因G06/G03/G17/G15回归失败的多轮运行全部保留为失败证据，不作为通过。
S7脚本`tools/evaluation/production_first_batch_e2e_20261028.py`已实际运行并成功；旧backup/publisher事故（FL-D483/484）已修复。
MySQL独立实例已在本机3308临时数据目录启动（非生产库），`tests/test_db_mysql.py` **6 passed**，可作为后续并发/迁移验证；凭据仅运行时环境，不写入仓库或文档。不得把该测试指向生产`fundlex`库。生产DB+对象备份已生成/verify并在隔离MySQL恢复测试54表/93users/711docs；测试库已删除。
