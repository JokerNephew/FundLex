# 首批真实修改评测结果（进行中）
日期：2026-10-29。**不是28份准确率，也不是全项目通过。** 当前只有价值优选 B02 完成新引擎真实运行并通过独立业务复核；其余20 dev/7 holdout待跑。

## 样本与版本
- 源：`funds_word/基金合同第一批/广发价值优选混合型证券投资基金基金合同.docx`，SHA256 `708bca5d...`。
- selection：`var/recall-first-evaluation/first-batch-20261028/selection-first-batch-20261028.json`，B02 dev。
- 标签：`docs/evidence/labels-first-batch-20261028-v2.json`（独立模型gpt-6-luna + MiniMax复核；51条未解决findings单列uncertain）。
- 引擎：当前`codex/comprehensive-remediation-20261028`；file-level真实运行`/tmp/opencode/comprehensive-remediation-20261028/real-value-first7`。
- 模型：新endpoint `https://api.commandcode.ai/provider/v1`，`deepseek/deepseek-v4-flash`，context32000 chars，max output32000，thinking disabled/low；账本仅观测。

## 结果
| 项 | 结果 |
|---|---|
| 任务交付状态 | complete |
| targets / edits | 29 / 16 |
| 模型调用 | 28；约$0.0742341；527秒（单进程） |
| final SHA | `bd97b693db002e68894498455f72caafc180ab11499a13c219c2e39d88e85027` |
| 机械校验 | final/redline与report哈希一致；final无修订；16 ins/16 del（作者资金清算部）；接受全部=final、拒绝全部=source；16个计划位置一致 |
| v2标签评分 | B02 **21/21 completed**，false_complete=0 |
| 独立业务复核 | **通过（P2：p800/p801为空段，建议清理；不阻断内容）** |
| 旧摘要缺陷 | p1258旧支付句0残留；新直销/非直销/365天/超一年返还完整；p802正文1份、p1258摘要1份，无重复 |
| 范围外 | 类别/费率/公式/管理费/托管费/余文保留，未发现范围外替换 |

证据：`docs/evidence/value-first7-score-20261029.json`、`docs/evidence/value-first7-business-review.md`；原始目录保留`/tmp/opencode/comprehensive-remediation-20261028/real-value-first7/`。

## 失败与限制（必须保留）
- first4在同一代码修复前曾把G16正文插入p799/p802两份，独立复核不通过；first4作为失败证据保留，不能合并计入通过数。
- first/first2/first3因mode/4k/12k reasoning截断；first6因旧/无效API key报`MODEL_HTTP_ERROR`。这些不是业务质量结果。
- 本结果是 B02 单合同事后独立复核，不是运行前冻结gold，也不是28份正式指标；1份通过不能外推整批或514份。
- Word/WPS往返、MySQL并发、真实飞书、生产部署及正式用户E2E仍未在此文件中完成；后续以生产结果更新。
