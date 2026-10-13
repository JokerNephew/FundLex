# FundLex AI 局部修改实际实现与评测结果（v2）

日期：2026-10-13。范围：在用户允许推翻“新增文字逐字来自固定模板”之后，完成“业务规则约束下的 AI 定位、局部修改和验证”实际应用链路，并用真实模型、非空编辑计划、修订版/最终版产物与独立评分给出客观指标。

本记录区分三类证据：**代码/夹具确定性验证**、**真实模型注册运行**、**人工/子 agent 参考标签**。AI 验证通过不构成语义正确性的数学证明；独立 AI 盲核不是外部业务审批。

## 1. 支持范围与执行模式

- v2 语义契约首版 **6 个 action**：R01-A1、R02-A1（按当前合同实际类别生成直销豁免条款，替换旧 A/C 槽位机制）、R03-A3、R04-A1、R11-A1（代码识别后精确删除）、R10-A1（模型定位 + 生成 + 独立验证的费用归属条款替换）。
- 其余 16 个 action 不在 v2 支持范围，仍保持 v1 只读诊断；不因本轮结果视为已评估。
- v2 运行固定为隔离评测：`execution_mode=evaluation`，产物 kinds 为 `evaluation_redline` / `evaluation_final`，存储在服务端持久化执行模式并据此校验下载；正式 `final`/`redline` 下载不生成。文件名或界面标签不构成隔离边界。
- v2 规则包 loader 拒绝任何 `auto_write`/`approved` 标签的包：打开正式写入需要另行发布行为，编辑布尔值不能启用。
- 支持范围内承诺：单段连续可写范围；跨段（P13 的 R03 语义目标）、跨 cell、结构屏障、同段无法唯一定位时明确失败关闭。
- **明确局限**：代码核查只能核对“已提取事实”，无法发现生成器与检查器同时漏提的限定或例外；`content_verified` 不等于全部业务语义已被证明。模型判读与事实引述可能出错，第二次检查只能降低而不能消除风险。

## 2. 实现的契约与流水线

- 规则包：`rules/compile_v2.py` 从冻结 v1 来源指引编译 `rules/rules_v2.json`（含 `rules_v2.py` 严格校验）。每个 action 明确：主体、行为、条件、费用归属、允许变化、必须保留、禁止新增、依赖证据、不支持条件与逐条 requirement（代码可核查 vs 模型核查）。
- 定位：`fundlex/v2.py` 在指定区域（正文/摘要、章节与子节别名）枚举目标；模型只提议逐字引文，字符坐标由代码在源投影计算；句首前缀、禁止内容、句读边界、编号前缀（如 `5、`）统一处理；末尾空格统一裁剪（`trim-inline-whitespace-sentence-span-v1`）；重复正文/摘要引文复用同一生成，但要求合同角色引文仍存在于对应位置。
- 生成：专用 `generate_clause` 任务，仅提交单个目标段落上下文与规则要求，不拼接整份合同；允许局部新文，禁止模型给坐标、文件、路径或验证标志。
- 验证：代码硬检查（JSON、范围、结构、操作许可、数字/单位、类别覆盖、禁止条件、长度）+ 独立 `verify_content` 任务（不接收生成器解释；逐条 satisfied/unsatisfied/unknown 且引文必须来自其声明来源）。事实引述按角色绑定（contract=目标段落原文，rule=规则文本，profile=画像事实），角色不匹配即拒绝。
- 执行权：`record = {源/位置/原文/新文哈希、规则/引擎/提示版本、事实与角色、要求结果、模型事件}` 由服务端组装并哈希；`verify_content` 或生成器的自填状态不能获得执行权。DOCX 发布边界用可信闭包再次运行代码检查与角色引文核查（content_check），篡改替换文本、记录哈希、规则版本或事实角色都会被拒绝。
- 产物：同一冻结计划生成红线的 `evaluation_redline.docx` 与接受修订后的 `evaluation_final.docx`；沿用既有 package/revisions/final_equivalence/non_target 校验，增加 `content_verification` 检查；正文与摘要整组一致性：同一 action 所有已验证目标的新文必须一致，否则整组回滚；任一目标失败时该 action 原子回滚（不留下半应用的修改）。
- 已符合识别：替换类动作先对源文运行代码要求检查，已合规段落标记 `V2_ALREADY_SATISFIED` 且不调用生成模型（P06、U04 实测生效）。

## 3. 旧 A/C 槽位限制的移除与验证

旧 v1 的 R01-A1/R02-A1 模板含 `A类基金份额`/`C类基金份额` 槽位，`TEMPLATE_VARIANT_UNAPROVED` 使这些动作永远不能写入，单纯打开 `auto_write` 无法解决。v2 不再使用槽位或固定文案相等：生成与核查都以**当前合同实际类别与收费证据**为准。

独立夹具（`tools/evaluation/v2_fixtures.py`，期望在运行前冻结）验证：

| 夹具 | 场景 | 结果 |
| --- | --- | --- |
| FX01 | H/J/K 非 A/C 类别 | 生成条款逐一点名 H、J、K，不含 A/C 字面；写入成功 |
| FX02 | F 组申购费；D/E 同组费率不同（0.4%/0.2%） | 逐一命名 F、D、E，新文不含任何费率数字；写入成功 |
| FX03 | 类别收费属性证据不足 | R02 拒绝（PROFILE_EVIDENCE_INCOMPLETE），不写入 |
| FX04 | K 类同时收申购费与销售服务费（混合收费） | 拒绝（V2_HYBRID_CLASS_FEE_UNSUPPORTED），不写入 |
| FX05 | 正文与摘要相同定义 | 复用同一新文，两处一致写入（2 处编辑） |

夹具注册运行 `fixtures-v2`：5/5 通过（3 份实际修改、2 份按语义拒绝）。真实合同上同样验证：P08（A/C/D/E）生成的条款为“申购本基金 A 类、D 类基金份额时，不收取认购/申购费用；通过直销机构申购的 C 类、E 类基金份额，不收取销售服务费……”，与合同实际类别与费用分组一致，未出现按名称或文件名分支。

## 4. 注册运行与客观指标

评分器 `tools/evaluation/v2_compare.py` 直接读取下载后的**实际修改 DOCX**：按文档段落重算最终文本、独立重放编辑、区分严格范围与纯空白差异；只统计独立盲核已标注的动作，其余动作/范围的编辑单独列出（本轮为 0）。

### 4.1 已有 16 份（开发回归集，含 R10 真实生成）

源：`action-pilot-20261013\inputs`（16 份，gold SHA `76f65517…` 未变；旧分数保留）。运行：`pilot-16b`（中间引擎）与 `pilot-16c`（最终引擎，engine `e48c7778…`，规则 `e184f70d…`）。最终引擎结果：

| 动作 | 应改目标 | 正确修改 | 编辑精度 | 目标完成率 | 备注 |
| --- | --- | --- | --- | --- | --- |
| R03-A3 | 5 | 5 | 1.0 | 1.0 | 含 P09/P15 等 |
| R04-A1 | 4 | 4 | 1.0 | 1.0 | P12/P13/P14/P15 |
| R11-A1 | 3 | 3 | 1.0 | 1.0 | 精确句范围 |
| R10-A1 | 4 | 4 | 1.0 | 1.0 | P08 精确 42..164，前缀申购费内容保留；P01/P03/P05 |
| 合计 | **16** | **16** | **1.0** | **1.0** | 另 1 处已符合（P06）正确不改 |

- 误改：0；负例区域变更：0；范围外额外编辑：0；正文/摘要冲突：0；修订等价/非目标校验：全部通过。
- 应改目标 16/16 全部精确（严格范围，无纯空白差异）；13 份应处理合同全部业务与文件检查正确 → 自动完成率 13/13 = **1.0**（注：该完成率按独立标注范围计；引擎自身交付状态另列）。
- 引擎交付状态（16 份）：8 evaluation_modified、1 evaluation_unmodified（P06 已符合）、4 incomplete、3 not_generated（P04/P10/P16 类型排除）。
- 未通过的 action 原因（均为拒绝而非误改）：R01/R02 事实角色不匹配 4 次（模型引述未绑定角色，服务端拒绝）、跨段目标 1 次（P13，预期）、R10 定位未找到 1 次（P11，该合同不属标注目标）、费用归属段排除 7 次（R11 非目标宿主）。
- 中间引擎 `pilot-16b` 同样 16/16；此前 `pilot-16`（旧引擎）为 11/16，修复记录保留。

### 4.2 未见样本泛化（8 份，运行前独立盲核冻结）

选择：`tools/evaluation/select_unseen.py` 从 `funds_word/` 按名称排序等距抽取 8 份，排除全部 16 份 pilot 源；盲核子 agent 在**未看到任何预测**时按冻结口径标注（gold SHA `e1c67fa5…`，`predictions_read:false`），标注引文全部机器复核。

- 注册泛化运行 `unseen/run`（修复前引擎）：资格 6/8；已标注目标 4/6（R10 4/5、R03 0/1）；负例违规 0；已符合 1 正确不改；自动完成 4/6 = 0.667。
- 该运行发现两个真实缺口并在随后修复（原运行保留）：(a) 类别字面 `黄金交易型开放式证券投资基金`、`混合型基金中基金（FOF）` 未通过类别证据校验（U01/U06 资格失败）；(b) 子节标题嵌入前段（`基金存续期限不定期八、基金份额类别`）导致 U07 的 R03 范围未建立。
- 修复后诊断运行 `unseen-fixed/run`（**该 8 份已用于发现缺口，不再视为未见验证集**）：资格 8/8 一致；已标注目标 6/6 正确 + 1 已符合不改；编辑精度 1.0；负例违规 0；自动完成 6/6。
- 修复后仍失败关闭的项（如实报告）：U04 R01 因段落已存在部分直销条款拒绝（`V2_EXISTING_CLAUSE_UNSUPPORTED`）；U07 R01、U08 R02 因模型事实引述角色不匹配拒绝（`V2_FACT_ROLE_MISMATCH`）。这三份的引擎交付状态为 incomplete（标注范围内仍全部正确）。

### 4.3 指标定义与本次数值

- 编辑精度 = 正确实际编辑 / 全部实际编辑（分母不含未执行的拒绝项）。本轮 16 份与未见集均为 1.0；拒绝、漏改进入完成率分母。
- 目标完成率 = 正确修改 / 全部应改目标（含拒绝与漏改）。16 份 = 16/16；未见注册 = 4/6；未见修复后诊断 = 6/6。
- 保持要求满足率、非目标变化、正文摘要冲突、修订等价失败：本轮均为 0 违规（由产物校验与评分器重放共同确认）。
- 完整自动交付率按“独立标注范围内的业务与文件检查均正确”计；引擎交付状态（含标注范围外动作的失败）单独列出，不合并夸大。

## 5. 真实模型用量、预算与延迟

- 模型：`deepseek-flash`（供应商返回的 alias，非不可变快照；通用请求选项关闭思考模式），供应商中立配置；密钥不落盘、不入库。
- 共享账本（保留旧账、不清零）：累计 **611/680 次 HTTP**，估计 **USD 0.396947/0.70**（输入 0.3/M、输出 1.2/M 配置价，非供应商账单）。其中 v2 工作新增 493 次、约 USD 0.3417；包含早期脚手架迭代与修复重跑，全部保留。
- 注册运行用量（最终引擎 e48c7778…，规则 e184f70d…）：

| 运行 | 文档 | HTTP | prompt+completion tokens | 估计费用 | p50/p95 延迟 | 交付 |
| --- | --- | --- | --- | --- | --- | --- |
| fixtures-v2 | 5 | 16 | 10,999 + 5,590 | USD 0.010008 | 8.9s / 9.5s | 3 modified, 2 incomplete（语义拒绝） |
| pilot-16c | 16 | 87 | 74,273 + 34,414 | USD 0.063579 | 20.7s / 27.8s | 8 modified, 1 unmodified, 4 incomplete, 3 excluded |
| unseen-fixed | 8 | 38 | 29,982 + 13,797 | USD 0.025551 | 17.1s / 28.6s | 3 modified, 3 incomplete, 2 excluded |

- 限流 0、模型错误 0（注册运行）；预算上限未达到；无拼接多份合同全文；并发 1、分段小批。

## 6. 失败、拒绝与不支持（明确列表）

- 支持范围外（保持 v1 只读）：其余 16 个 action；跨段/跨 cell/结构屏障目标；同段无法唯一定位；混合收费类别；类别证据不足；已存在部分直销条款段落（避免重复写入）。
- 模型侧失败关闭（本轮实测）：事实引述未绑定角色、验证返回 unsatisfied/unknown、定位未找到、输出 schema 无效。均不写入，原因入报告。
- 已修复缺口（原始运行保留）：类别字面变体、嵌入式子节标题。
- 未完成/未验证：未见集在修复后已非“未见”；R04-A1/R11-A1 在未见集无应改目标，无法在该集合验证泛化；每 action 30 正例/30 反例/多种结构的发布门槛远未满足。

## 7. 正式发布条件（尚未达到）

1. 22 个 action 仍全部 `auto_write=false`；本轮的 6 个 action 未取得离线发布批准或独立数量门槛，v2 loader 继续拒绝开启写入。
2. 独立 AI 盲核不是外部业务真值；R10/R03 等标注口径未获业务专家批准。
3. v2 支持范围外的 16 个 action 未实现语义契约；正文/摘要以外的结构变体未系统评测。
4. 生产身份、数据库、对象存储、容量与费用上限仍按既有上线前清单处理；本地评测为 SQLite/单 worker。
5. 真实质量还需覆盖更均衡的未见样本（含更多 R04/R11 应改目标）与已知答案的语义变异夹具批量回归；本轮仅含 6 个构造夹具与确定性变异单测。

## 8. 复现命令

```powershell
# 1) 夹具与规则包
.venv\Scripts\python.exe -X utf8 rules\compile_v2.py
.venv\Scripts\python.exe -X utf8 tools\evaluation\v2_fixtures.py --output <eval>\fixtures
# 2) 真实注册运行（先在环境登记共享账本与上限；模型 alias 只在该子进程设置）
$env:LLM_MODEL='deepseek-flash'; $env:FUNDLEX_MODEL_LEDGER='<pilot>\pilot_budget.sqlite'
$env:FUNDLEX_MODEL_MAX_REQUESTS='680'; $env:FUNDLEX_MODEL_MAX_COST_USD='0.70'
$env:FUNDLEX_MODEL_CONCURRENCY='1'; $env:FUNDLEX_MODEL_MAX_OUTPUT_TOKENS='2500'
$env:FUNDLEX_MODEL_REQUEST_OPTIONS_JSON='{"thinking":{"type":"disabled"}}'
.venv\Scripts\python.exe -X utf8 -m tools.evaluation.v2_pilot --input <docx dir> --output <run dir> --expected-count N --batch-size 1
# 3) 评分（读取实际修改后的 DOCX）
.venv\Scripts\python.exe -X utf8 -m tools.evaluation.v2_compare --mode gold --root <gold root> --run <run dir>
.venv\Scripts\python.exe -X utf8 -m tools.evaluation.v2_compare --mode fixtures --root <fixtures dir> --run <run dir>
# 4) 全量测试
.venv\Scripts\python.exe -X utf8 -m pytest -q -p no:cacheprovider
```

私有运行位置（不在仓库内、不提交）：`C:\Users\asus\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Local\FundLex\v2-evaluation-20261013\`（fixtures、fixtures-run…fixtures-v2、pilot-2/2b、pilot-p08、pilot-16/16b/16c、unseen、unseen-fixed、各自 protocol/manifest/summary 与下载产物）；旧 pilot 与冻结 gold 原样保留。

## 9. 自检声明

- 未修改任何合同原件、旧 gold、旧运行记录或旧分数；未见集标签在预测前冻结，修复后重跑明确标注为诊断而非未见。
- 未把 AI 二次检查称为确定性证明；未把拒绝多描述为可用；未按结果倒推发布阈值。
- 全部新增业务事实来自规则包要求或合同证据；模型字面、坐标、验证标志均不能直接获得执行权。
