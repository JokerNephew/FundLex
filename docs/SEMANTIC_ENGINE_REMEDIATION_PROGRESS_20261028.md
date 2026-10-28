# 修订引擎整改执行进度

更新：2026-10-28（S0–S1 完成，S2/S3/S4/S5/S6 首批已实现并离线验证；S7–S11 未完成）。**本表不是真实模型、生产部署或用户端到端验收声明。**

主方案：[SEMANTIC_ENGINE_REMEDIATION_EXECUTION_PLAN_20261028.md](SEMANTIC_ENGINE_REMEDIATION_EXECUTION_PLAN_20261028.md)。接续入口：[执行Prompt](NEXT_AGENT_SEMANTIC_ENGINE_EXECUTION_PROMPT_20261028.md)。

## 1. 当前真实起点

- 工作区 `/home/opencode/fundlex`，Linux本机云服务器，Python `.venv/bin/python`。
- 规划时分支 `codex/regulation-guide-generation`，HEAD `99a5dad27aa68e73362851d136bd0955944707ea`；大量dirty/未跟踪依赖需在S0保护，不能只切旧HEAD。
- 业务边界：规则对应范围外不改、不额外去重。范围按指引和完整条款语义，不按漏选scope定义。
- 历史审计95 passed/全量1803 passed等只代表过去版本/适用范围，不能填写成本方案的新验收。
- 当前工程总状态：**进行中 / NO-GO**。本轮真实模型调用0、费用0；未改合同/未部署。离线全量测试 **1846 passed / 13 skipped**（2026-10-28 本轮代码）。
- 执行分支 `codex/semantic-engine-remediation-20261028`（从 `99a5dad` 带 dirty 树创建）；可恢复基线 `/tmp/opencode/semantic-remediation-baseline-20261028-150805/`（tracked patch、index patch、untracked code tar、578份合同 sha256）；本批代码快照 `/tmp/opencode/semantic-remediation-slice-20261028-162300/`。
- **未提交 Git commit 的原因**：`recall.py`/`recall_pipeline.py`/`effects.py`/`claim_replay.py` 在本任务前已有约 2873 行未提交改动，直接提交会混入无关工作。S0 的“逐文件/hunk 建立审阅基线”仍未完成，当前以补丁快照保证可恢复；下一执行者必须先完成基线分离再按阶段提交。
- 方案已由两名只读agent分别审阅语义架构与测试/发布约束，均已完成，无本轮运行中的agent/任务。主agent已整合固定发布源/遗漏Guide Worker及第一批历史预测不构成新独立留出的风险；这些是规划证据，不是修复成果。
- 保存验证：`git diff --check`通过；三份新文档的本地链接、结尾换行、代码围栏配对通过；主方案R01–R17及S0–S11齐全。仅为文档验证，未执行工程验收测试。

## 2. 阶段状态

| 阶段 | 状态 | Owner | commit / 证据 / 阻塞 |
|---|---|---|---|
| 方案和接续说明保存 | 已完成 | 本轮主agent | 方案+Prompt+进度表 |
| S0 保护起点与版本基线 | **部分完成**：快照/分支完成；基线分离未完成 | 主agent | 未提交；见上方原因 |
| S1 版本化契约与正负例 | **已完成（离线）** | 主agent | `fundlex/semantic_evidence.py`；`tests/test_semantic_evidence.py` 10 passed |
| S2 多叶子scope与独立覆盖 | **部分完成**：多叶子/费用标题/copy_key已实现；独立覆盖扫描未实现 | 子agent A | 景宁 p148+p155 同 scope；`test_rule_scope_multileaf.py` |
| S3 统一re-quote/语义批准 | **部分完成**：批准消费链已贯通planning与site waiver；T3/全链路re-quote未统一 | 主agent | 弘利G17 0调用完成有界删除；G14绑定通过 |
| S4 事实/适用性/无目标义务 | **部分完成**：无站点字面缺失不再PASS；事实语法/依赖未改 | 子agent B | `test_effect_semantic_residual.py` |
| S5 执行器与重试联合规划 | **部分完成**：批准span删除、delete重试污染修复；registry通用升级未做 | 主agent/子agent B | `approved_span_delete`；FL-D442 |
| S6 实际产物语义证明/交付 | **部分完成**：重复效果按operation/site收敛；完整artifact语义复核未接 | 子agent B | `test_claim_duplicate_scope.py` |
| S7 分页/预算/恢复 | **部分完成**：`structure_index` 默认全量；12/20/40与长段未做 | 主agent | 85节全部索引 |
| S8 结构能力/前后端集成 | 未开始 | 待分配 | 共享模块回归、真实前端 |
| S9 独立标签/真实优化回归 | 未开始 | 待分配 | 固定分母、第一批来源映射、预算 |
| S10 发布与用户E2E | 未开始 | 待分配 | 默认入口真实模型/下载/鉴权 |
| S11 交付与接续归档 | 未开始 | 待分配 | GO须有完整证据 |

## 2.1 本轮已落地的行为（离线证据）

证据：`docs/evidence/remediation-probe-20261028.json`，复跑 `tools/evaluation/remediation_probe_20261028.py`，`model_calls=0`。

| 行为 | 修改前 | 修改后 |
|---|---|---|
| 景宁 G05 scope | 只含 p147–p149 | 同时含 p148、p155（均为 body） |
| 弘利 G17 p784 | `TARGET_SOURCE_MISMATCH`，0调用即拒 | 批准waive site词表，`approved_span_delete` 精确删除该句，0调用 |
| 无站点删除证明 | guide字面缺失→PASS/VERIFIED_ABSENT | `OPEN/UNPROVEN`，需显式覆盖证据 |
| 结构索引 | 默认80节截断 | 默认全量（85/85，尾段可达） |
| delete compose重试 | 二次正确仍报首次错误 | 每次attempt独立校验 |
| G14重复“基金” | 绑定失败 | 归一化后可绑定表述2 |

## 2.1.1 第二批（提交 `2953a87` 及之后）

- T3/定位：`locate_unresolved_targets(approvals=...)` 接受“候选窗口内真实 quote + 有效批准”，词袋不命中只记 `anchor_bypassed`；无批准/越界/伪造/过期仍拒。候选发现可分页（第13个可达，带 `has_more/remaining/next_cursor`）。
- 事实：`derive_fact_statuses` 按申购费/销售服务费分别推导，未知服务费不再抹掉已证实申购费组。
- 分页：`replay_claims`/`check_delete_residuals` 到40边界返回 `truncated/remaining/next_cursor`；`ensure_delete_targets` 支持 `cursor/page_info`，pipeline 循环取页并在页预算耗尽时记 `coverage_gaps`。
- 交付分类：`EFFECT_SITE_UNPROVEN` 等新码归为阻断，未知码 fail-closed。
- 执行器升级：确定性执行器无法表达变体时，**有有效批准**才允许受控 compose fallback；无批准仍 `RECALL_ROUTED_EXECUTOR_UNAVAILABLE`（commit `102435a`）。
- 事实语法：集合枚举接受“现有/设/包括”等真实写法（仍要求标签集合与当前类别完全一致）；收费证据识别“实行/适用 …% 年费率”。

## 2.2 仍需立即处理的高优先项

1. **S0基线分离**：把本任务相关改动与既有dirty工作分开，形成可审阅commit；否则无法安全发布。
2. **S3全链路**：T3/append/audit仍各自检查；`claimed_operations`仍不能升级为批准。
3. **S4事实**：`derive_fact_statuses` 共享fee_status耦合、集合/收费固定语法未改。
4. **S6接线**：`absent_coverage_by_operation` 尚未由pipeline提供；新失败码 `EFFECT_SITE_UNPROVEN` 需纳入交付分类（当前会如实未完成，不会假complete）。
5. **S7分页**：候选12、删除20、失败40、sweep/rounds仍未分页。
6. **S8–S11**：真实前端、独立标签、真实模型、生产发布与用户E2E全部未做。

S1后S2/S4及部分测试可并行；S3依赖S2/契约，S5依赖批准/事实，S6依赖规划契约，S7/S8可隔离模块并行，S9须等集成稳定，S10须等S9门槛通过。共享文件采用单写者，不机械按阶段表串行等待所有独立工作。

## 2.3 本轮提交记录（分支 `codex/semantic-engine-remediation-20261028`）

| commit | 内容 |
|---|---|
| `f2e318e` | 语义批准/多叶子scope/真实证明首批（含引擎dirty基线） |
| `2953a87` | 批准感知locator、事实分族、候选/删除/失败分页、交付分类 |
| `102435a` | 有批准才允许受控compose升级；集合枚举/收费“实行”语法 |
| `af2acd7` | 批准变体升级回归测试 |
| `e9ce4f6` | 截断的残留扫描计入未完成 |

未提交：既有frontend/compare/feishu等无关dirty工作保持原状，未混入以上提交。

## 3. 执行时每项必须填写

- task_id/R编号/现有FL编号及标题；owner/分支/worktree；允许编辑的文件/接口版本；依赖；退出测试。
- 期望行为来源、反例、实际test命令/数量/版本/证据路径；未验证项与下一动作。
- 共享预算账本路径及授权cap、已用/预留/剩余；所有HTTP重试和子agent模型消耗计入。
- 冻结source/guide/labels/engine/prompt/schema/model配置hash；候选与生产diff；发布/rollback记录。
- 运行agent/进程、是否占用共享文件/预算；每阶段后清理ownership但保留证据。

## 4. 下一条可执行动作

1. 完成S0基线分离：按文件/hunk把本任务改动从既有dirty工作拆出，形成可审阅commit（当前代码已在工作树并通过离线回归，但尚未提交）。
2. 继续S3：把统一re-quote接入T3/append/audit；让approved记录成为唯一语义授权，`claimed_operations`只留审计。
3. 继续S4：拆分事实依赖、接入独立语义复核；给pipeline接`absent_coverage_by_operation`并把`EFFECT_SITE_UNPROVEN`纳入交付分类。
4. 继续S7：候选/删除/失败/轮次分页与`remaining/cursor`可观测。
5. 然后S8–S11：真实前端、独立标签、真实模型评测、受控发布、默认入口用户E2E。
**不要直接先部署，也不要只修G14一个字面特判；不得用未提交的混合dirty树发布。**
