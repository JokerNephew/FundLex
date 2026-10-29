# 首批真实修改评测结果（进行中）
日期：2026-10-29。**不是28份准确率，也不是全项目通过。** 当前只有价值优选 B02 完成新引擎真实运行、生产浏览器E2E并通过独立业务复核；其余20 dev/7 holdout待跑。当前代码全量非浏览器回归 **2118 passed / 6 skipped / 676.41s**，浏览器 **69 passed**；这些是工程回归，不是质量分母。

## 样本与版本
- 源：`funds_word/基金合同第一批/广发价值优选混合型证券投资基金基金合同.docx`，SHA256 `708bca5d...`。
- selection：`var/recall-first-evaluation/first-batch-20261028/selection-first-batch-20261028.json`，B02 dev。
- 标签：`docs/evidence/labels-first-batch-20261028-v2.json`（独立模型gpt-6-luna + MiniMax复核；51条未解决findings单列uncertain）。
- 引擎：当前`codex/comprehensive-remediation-20261028`；file-level真实运行`/tmp/opencode/comprehensive-remediation-20261028/real-value-first7`。
- 模型：新endpoint `https://api.commandcode.ai/provider/v1`，`deepseek/deepseek-v4-flash`，context32000 chars，max output32000，thinking disabled/low；账本仅观测。

## 结果：本地隔离运行 first7
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

## 结果：正式生产浏览器 E2E（2026-10-29）

| 项 | 结果 |
|---|---|
| 入口 | `https://fundlex.club`，正式 V1 浏览器注册/登录/当前指引/上传/结果页/下载 |
| 任务/文档 | `6bbb6712e9a34b6bbfb2400e239ffc09` / `5d35ba80d3414de49e93e4bccabe06e0` |
| 生产候选 | `cdf298e`；engine `25308351015fd895936c49d133b3ab5129828be3e27dc792ccff526e2299a130`，service `e0625b495b5cea8ad1078467ce7203b60df02091f929d042c957ecde63fd9d73` |
| 真实模型 | `deepseek/deepseek-v4-flash`，27逻辑/27HTTP，140269 prompt +100370 completion tokens，约$0.08126235，651.2秒 |
| 交付状态 | complete；16 changes，16 ins/16 del，final `4f0a10abc0c58fadc25561e3de6b21f167441848838b7f6e253f641d94f96707`，redline `0b394535a2201910123bc7dabc33b5b7d5ce235ea3e45f8d6eb5398c09651552` |
| 机械校验 | 10/10：源/产物hash、文件对、接受=final、拒绝=source、final无修订、段落位置、计划实际一致 |
| v2标签评分 | B02 **21/21 completed**，false_complete=0 |
| 独立业务复核 | **通过（无P1；P2：p800/p801空段建议清理，不阻断）** |
| G06/G15/G16/G17 | p128禁令句已删；p800旧支付已删；p802正文与p1258摘要各1份新机制；p801用途/募集期句已删 |
| 范围外 | A/C、0.40%、公式、管理费/托管费、p803余文保留；未发现范围外替换 |

证据：`docs/evidence/production-value7-result.json`、`docs/evidence/production-value7-score-20261029.json`、`docs/evidence/production-value7-business-review.md`；原始下载目录`/tmp/opencode/comprehensive-remediation-20261028/production-value7-20261029/`。

**边界**：生产E2E只覆盖1份真实合同；P2空段未清理；20dev/8holdout其余、全量514+、Word/WPS、真实飞书、全部法规/Compare生产E2E仍未完成。不得把本份通过写成全项目或全量准确率通过。

## 失败与限制（必须保留）
- first4在同一代码修复前曾把G16正文插入p799/p802两份，独立复核不通过；first4作为失败证据保留，不能合并计入通过数。
- first/first2/first3因mode/4k/12k reasoning截断；first6因旧/无效API key报`MODEL_HTTP_ERROR`。这些不是业务质量结果。
- 本结果是 B02 单合同事后独立复核，不是运行前冻结gold，也不是28份正式指标；1份通过不能外推整批或514份。
- Word/WPS往返、MySQL并发、真实飞书、生产部署及正式用户E2E仍未在此文件中完成；后续以生产结果更新。
