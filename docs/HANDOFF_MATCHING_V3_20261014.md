# 多对多匹配与实际 DOCX 复核接续断点

## 第二部分：第二次会话收尾（2026-10-14 下午）

**追加更新（当日傍晚，进行中）**：已接入 OpenCode Go 端点（`https://opencode.ai/inference/go/v1`，模型 `deepseek-v4.1-flash`，需 `x-opencode-session` 稳定会话头与自有 User-Agent；用 `FUNDLEX_MODEL_EXTRA_HEADERS_JSON`/`FUNDLEX_MODEL_USER_AGENT` 配置；本地 Windows 用户级环境已切换）。后续协议修复：段落模板变体**尾句相关度保护**（拒绝吞掉尾部义务句，修复 U07 类内容丢失）、**空变体答复记为 `V3_VARIANT_NOT_FOUND`**（不再连坐回滚同动作其余目标，修复 P14 类）、模型判定类证据的空/不可用引文改走**一次有界复核**（修复 P15 类）、后验上下文新增 **`PUBLISHED_OLD_TEXT`** 供保留检查对照；P08 R15-A2 经产品负责人裁定为**标签分歧**（整句删除正确，标签与阈值未改，处置见 `IMPLEMENTATION_PLAN.md`）。最终证据运行 `final4-fixtures/final4-unseen8/final4-pilot16` 已启动（引擎 `6dc8357c…`、规则 `e9aeef0a…`、461 测试通过、审计 22+23）；跑完后按下述清单评分→发布→交付复验。

**冻结状态**：引擎 `8a914ddb3e7aa1c0574786c5a4beef706fae8a7e2f4f17d2133ad5c013c117ab`；规则包 `e9aeef0a5bc9a89f1e055ff67d39d2c97e1c8834d39c46808bfa5fe6fade7a33`（未发布、22 动作、草案同步）；全套 **454 passed**（含 MySQL 实库）；确定性审计 **22 正例 + 23 反例全过、0 错误写入**（`var/matching-upgrade-20261014/audit-final2/`）。

**本轮修复（全部有测试）**：
1. 收尾断点要求：删除动作完整业务句边界（`V3_DELETE_SENTENCE_BOUNDARY`/`V3_DELETE_SENTENCE_MERGED`，防截半句与吞支付/公式）；R10 已符合独立语核验负例；相邻冲突、同章补找、0.3.0 门禁为上一轮已实现，本轮复核通过。
2. 来源重存：`references/source/…_文案勘误版.docx` 被重存（文本逐段不变），仅 `rules_v1.json.source_sha256` 9e1b7771→b77be53c，其余业务值未动；v1 新 SHA `c3edf647…`；`compile_catalogue.py`/`compile_v2.py` 写出 LF；v2 已按新来源重建。
3. 后验协议 v2（本轮新增）：必需 ID 指令化 + 一次有界补问；schema 不合规仅限单窗口（预算/服务停止仍上抛）；`OTHER_AUTHORIZED_EDITS` 披露同段其他动作授权修改；删除动作披露被删目标、允许 BEFORE 引用或 AFTER 邻近引用并由代码核验目标消失；**代码可证属性以代码为准**，模型异议记录 `model_dissents`；before 引文在产物中仍存在可用于 PRESERVATION/COVERAGE；仅模型判定类失败做一次有界复核（`consensus_event`）；区域数字检查忽略段首编号、数字类检查改查写入文字；无编辑窗口只查 PRESERVATION。

**证据运行（外部阻塞，未完成）**：
- `final2-fixtures`：3 修改（含例外）+ 2 设计内拒绝；动作级断言全过；夹具旧期望差异仅为交付状态口径与 FX03 拒绝标签（未改期望文件）。
- `final2-unseen8`：旧 gold 5/6（U05 R10 后验误拒，协议 v2 已修）、精度 1.0、越界 0。
- `final2-pilot16`：供应商 **HTTP 402（账户余额不足）** 于 P08/P09 安全停止；P01–P08 完成、P10–P16 未跑；旧 gold 部分 6/9、精度 1.0。
- 三次运行绑定引擎 a590c858，**对最终引擎已过期**，发布前必须重跑。

**续跑清单**（账户恢复后，全部命令沿用本文档第一部分与 `MATCHING_UPGRADE_EVALUATION_PROTOCOL.md` 的登记参数）：
1. 三组证据运行到新目录（fixtures / unseen / pilot16，`FUNDLEX_V2_STATE_DIR` 各自独立）。
2. `v2_compare`（fixtures 模式 + 两个 gold）与 `matching_audit`（labels SHA 73c42e92…）评分并归档。
3. `rules.release_v2 --audit-output var/… --evidence-run …×3`（部署环境变量，LLM_MODEL=deepseek-flash 等）。
4. 全套测试 + `task_revision_run` ≥2 份正式交付（final/redline、下载 SHA、例外清单）。
5. README/证据文档更新与按功能提交。
6. 注意：供应商 402 是外部余额问题；账本 cap 7500/6.0 仍有余量（现 3152 HTTP / 约 USD 2.99）。

## 第一部分：原断点（2026-10-14 上午）

2026-10-14 用户因额度即将用完，要求停止、保存并由另一个 agent 接续。所有子 agent 已中断，不应指望旧 agent 继续工作。这里覆盖实施计划较早的中间状态。

## 用户授权与目标

用户已批准自主开发、自己管理进度，不需重新请求开工许可。生产服务器 4C8G，具体并发由 agent 决定。改进主线：规则/action 与合同子节多对多匹配；代码找不到子节时模型在允许上级章节中补找；盘点全部目标；固定政策文案代码组装，R01/R02/R10受约束生成；临时修改后读取实际 DOCX 独立复核；失败整 action 回滚，重新生成后复核新组合；定位未知进入例外。全部22动作最终要可用，不能交只读半成品。

## 工作区和状态

- Windows 11 / pwsh，`D:\Desktop\FundLex`，分支 `codex/fundlex-implementation`，HEAD 仍 `0786f99`。本轮没有提交，没有 push；全部源码和新文件保存在当前工作区。
- 原已发布包完整备份于 `var/matching-upgrade-20261014/baseline/`，含 published/draft、旧31份报告、manifest及旧gold哈希；不要用旧发布包掩盖新代码尚未验收。
- 当前 `rules/rules_v2.json` 是由新 `compile_v2.build()` 准备的未发布评测包：`False / 22`，SHA `1df238e1b27dd277e90e3ad8a1cdaf976d2393cce878cf05e6271c113e53c9a3`。新草案与编译器之后还有修改，必须重新核对一致性。
- 停止时引擎 SHA `f860e586eddb27e2af5967e135eccb0c36e8a3c1969e91dff08afb6c947cbf7e`，仅作断点识别，不是已发布构建。
- 源码尚未最终冻结。`fundlex/api.py/jobs.py/rules.py/store.py`仍 CRLF，两个v2 JSON也仍CRLF。新增 `.gitattributes` 固定 Python 和 rules JSON 为 LF；最终冻结前规范换行并重新测试/评测。
- `rules_v1.json`只转换CRLF→LF，已机器断言规范字节完全等于HEAD git blob，没有改政策/门槛/结构；规范SHA `566b174088c5ea06bf809092abe251c597a1325072880536c9c06db25fde56e8`。compile来源hash应按稳定LF重新生成。不要重新改v1业务值。

## 已实现，仍需最终审查

- `fundlex/v2.py`：有界scope备用解析、剩余业务范围补找、模板变体最小核心定位、R10多独立目标、同原件计划、跨action冲突拒绝；目标引文自身的quote_all/quote_any核心检查。
- `fundlex/model.py` / `rules_v2.py` / `rules/compile_v2.py`：`resolve_scope`、`verify_artifact`、新提示scope/locate_variant/artifact_verify、policy_core契约和候选过滤。scope最多4调用/action，variant最多8候选/action。
- 新 `fundlex/artifact_review.py`：重新读取final实际章节，按段落分窗（最多3窗/action/轮），全相关章节覆盖，要求/PRESERVATION/COVERAGE证据回查；窗口无法保留重叠明确拒绝。指引来源不能单独证明写入成功；正向要求复验after引文代码checker，delete_only要求before引文等于实际删除目标。
- `v2_pipeline.py`，版本0.3.0：私有临时产物→模型后验→首轮整action撤销→新plan重生成且全部剩余action重新复核；二轮仍有拒绝则保守撤销全部修改，不开放文件。not_matched进入例外，Markdown附例外交付表述已修。
- `store.py`：v3发布/下载要求最终后验record、source/plan/双产物hash、完整action与目标覆盖；检查对方产物tamper；report-only后验拒绝支持实际Worker/API持久化。历史0.2.0下载兼容。
- 新测试：`tests/test_v2_matching.py`、`test_v2_artifact_review.py`、`test_v2_artifact_pipeline.py`、`test_v3_delivery_review_gate.py`、`test_evaluation_matching.py`。既有4份v2测试有配套行为更新，未删除测试。
- 评测工具：新 `matching_audit.py` 独立读取实际DOCX重放；range差异/未标注/uncertain不伪称正确或错误，另列待审。`v2_pilot.py`强制batch1/模型并发1、完整transport与上下文绑定、每份检查引擎漂移、调用bound及Windows峰值内存。`release_evidence.py`只计最终组合后验、原因按合同action去重。
- `release_v2.py`新增强制 `--evidence-run`：v3须有当前完整5+16+8真实记录，核对engine/rules/transport/prompts、源去重>=29、实际产物门禁；发布JSON指定LF。新功能需要真实验证该工具。

## 最新测试与明确未完成

- 基线357通过含MySQL是在改动前测的，不能声称新版本全套357通过。
- 协调agent亲自复跑过核心相关79通过；B/后验/旧评测/发布子集29通过；后验关联加强后16+8=24通过；storage及新增相关子集13+62通过。它们是不同时间且重叠子集，不能相加为总测试数。
- root最后 `tests/test_evaluation_matching.py` 5通过。尚未完成新版本完整pytest/MySQL回归。
- 最后确定性动作审计 `var/matching-upgrade-20261014/audit-diagnostic2/audit.json`：21/22正例、23/23反例；R13正例失败，疑因通用“调整费率或收费方式”误入variant候选。代码随后更新过候选，必须重跑确认，不能删该反例或默认模型成功来过门槛。
- 独立安全审查3问题：同章一个已知子节遮蔽另一未识别子节已补候选发现；R10正向关键词误判已符合已补独立`verify_content`（停止时代码已见到，最终测试待确认）；R15旁句错删已补quote核心过滤。**停止前最新补充要求仍待核实：delete不能只引“销售服务费主要用于”半句，必须完整逻辑句边界且不吞非目标支付/公式，补截半句与合段反例。**
- planner既有编辑器连相邻区间也拒绝，协调agent已要求planner同样撤销冲突action而保留无冲突action；确认最后代码/测试落地。
- 新业务真实模型调用0次，29份最终回归/评分、真实证据、新发布、正式任务交付2份复验全部未做。不存在新版本业务准确率或零误改结论。

## 标签、基线诊断和私有位置

私有根：`C:\Users\asus\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Local\FundLex`。

- 新冻结参考标签：`var/matching-upgrade-20261014/labels/{targets.json,freeze.json,README.md}`，SHA `73c42e92720f90fe1d9533d03e33d8471c5debf72d3e387a19f6bc0dca79888f`。24份/192case-action，137modify/34already_satisfied/19unsupported，40画像uncertain。只看原文指引，在新预测前冻结，非外部专家gold，禁止修改。
- 旧预测对照：`baseline/matching-pilot.json`、`matching-unseen.json`、`gaps.md`。137应改引用仅4处已执行正确；133未执行中2处P16资格排除。P05 R16摘要p1289、P13 R16摘要p1249有原旧字面仍not_matched；R06范围吞后续计算，P05 R13吞前置条件；U07收费服务组抽取不足。
- 原gold：`action-pilot-20261013/gold.json` SHA `76f65517be316f86fefe93fb2573b8ade106e21f93b7b4b78cc4b64041b51b9a`；`v2-evaluation-20261013/unseen/gold.json` SHA `e1c67fa53d6ce9a6cd0bdb4615ea477578c7dffccbf7fa61560d4156eaff8981`（请以baseline/manifest机器记录复核，禁止改gold）。
- 原真实基线runs：`v2-evaluation-20261013/rel-{fixtures,pilot16,unseen}`，正式旧复验`delivery-verify`。
- 新私有目录`matching-upgrade-20261014/spot-input/`已复制P05/P13用于诊断，尚未运行。
- 停止状态快照：`var/matching-upgrade-20261014/handoff/state.json`。

## 预算与服务器参数

共享账本`action-pilot-20261013/pilot_budget.sqlite`仍1798 HTTP、估计USD1.2809772，本轮没有消费。实施计划已预登记累计cap7500 HTTP/USD6，输入0.3/M、输出1.2/M，并发1、批大小1。账本不重置、不伪造；到任一上限即停。

已选部署参数：2 API进程、1 worker、模型并发1；`MAX_CALLS=192`、`CONTEXT_CHARS=20000`、`MAX_OUTPUT_TOKENS=3000`、`TIMEOUT_S=60`、`RETRIES=1`，thinking disabled，模型deepseek-flash。MySQL buffer pool初始1536M/max_connections40，需目标机验证；本机峰值不能当4C8G容量验收。密钥仅从进程/Windows用户环境安全继承，不输出或写文件。详见部署指南。

## 接下来的顺序

1. 先读本断点、规格、预登记协议，核对dirty workspace；不要重建或还原已有WIP。
2. 收尾上述安全边界和R13审计失败；统一LF并重新build草案/隔离包；完整测试含MySQL、node语法和22动作审计全部通过后冻结core。
3. 按登记预算跑P05/P13诊断，出现缺口保留旧run、修代码后重新冻结；随后最终5+16+8（8份是历史泛化回归，不能重新叫未见集）。
4. 运行旧gold scorer和新标签scorer，人工核实range差异/未标注编辑，遵守已登记验收条件，不倒推改阈值。
5. 汇总证据，用同模型环境 `rules.release_v2 --audit-output ... --evidence-run <fixtures> --evidence-run <regression> --evidence-run <historical>`重新发布；再全套测试和真实task_revision_run正式交付至少2份、下载SHA、例外核验。
6. 更新README/实施计划/结果/部署文档，审阅并按功能显式暂存提交；无push，var不入库。保护references/funds_word/原始PRD及设计/workbench/frontend未提交图片。
