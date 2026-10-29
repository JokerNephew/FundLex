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


## 第一波 20 份 dev 真实运行（2026-10-29，两次运行）

### 运行与代码
- 旧代码失败证据：`/tmp/opencode/comprehensive-remediation-20261028/first-wave-dev-{1..4}`，全部保留，不删除失败样本。
- 修复后重跑：`/tmp/opencode/comprehensive-remediation-20261028/first-wave2-dev-{1..4}`；另有 A50/富信/聚安/美国房地产/道琼斯/沪深300/弘利/锐意/集盛的定向 `fixcheck*`、`edge-run-*`。
- 代码范围：`4e07839`→`55e0406`；最新全量非浏览器回归结果以本轮最终日志为准（此前为 2144 passed/6 skipped）。
- 模型：`deepseek/deepseek-v4-flash`，thinking disabled/low，32k context/output；账本仅观测。

### 标签评分最终值（`p6_score` + v2 标签，20 dev）
- 报告 `complete`：15 份；标签判定 `actually_complete`：14 份；`false_complete`：1 份（B01 A50：19/21，2 个标签判 wrong；独立业务复核认为这 2 项属于标签口径差异，产物本身通过）。
- 标签完成数：**304/390（77.95%）**；完整通过的 14 份多为 20–23/22（B16 标签数 23）。
- 未完成：B05 弘利、B12 沪深300、B15 美国房地产、B17 道琼斯、B19 锐意；主要剩余为 G02/G04/G05/G09/G16/G18/G22 变体、compose/审计或事实问题，不能计入通过。
- 评分文件：`docs/evidence/first-wave2-dev-score-20261029.json`。

### 独立业务复核（实际 DOCX，不采信 report complete）
- **通过（15 份）**：B01 A50（摘要修复版）、B02 价值、B03 品质、B04 富信（重复修复版）、B06 恒昌、B07 恒鑫、B08 恒阳、B09 恒隆（P2：p255 类别互转禁令在 G06 scope 外，属产品待裁决）、B10 招利、B11 景宁、B13 沪港深、B14 睿明、B16 聚安（摘要修复版）、B18 鑫裕、B20 集盛。
- **未通过/未完成（5 份）**：B05 弘利（G02/G04）、B12 沪深300（G16）、B15 美国房地产（G09/G22）、B17 道琼斯（G02/G04/G05/G18）、B19 锐意（G04）。这些失败样本保留，不删除分母。
- 典型 P2：删除后空段、p246/p200 序号丢失、摘要/正文残留旧尾句；不影响本份内容完整性但应在定稿前清理/确认。

### 结论
- **第一波不是 20/20，也不是 28/514 或全项目通过。**
- 当前可确认：生产 B02 单合同通过；第一波 **15/20 业务复核通过**，5 份仍有真实规则变体/compose/审计失败；标签层面 14/20 actually complete、1 份 false complete（B01 的 2 个标签口径争议，业务复核通过）。
- 共同代码版本：最新 `6539437`（全量非浏览器 **2158 passed/6 skipped**）；B01/B04/B16/B20 的定向重跑分别见 fixcheck8-a50、fixcheck6-fuxin、edge-run-1/003、edge-run-3/003。
- 下一步：处理 B05/B12/B15/B17/B19 的剩余变体（尤其 G02/G04/G16/G09/G22），冻结版本后跑 8 份 holdout，再扩样。
