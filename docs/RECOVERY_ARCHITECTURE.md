# FundLex Recovery Architecture（2026-10-20）

本文件描述本轮 `refactor/recovery-architecture` 的核心架构、接线点、配置方法与验证证据。
它是[生成策略 v4](GENERATION_STRATEGY_PLAN_2026-10-19.md)之后的统一收口，不替代业务指引与集中问题记录。

## 1. 目标与不变量

系统按以下顺序处理每个义务：

```text
Guide → Obligation IR → Evidence-backed Facts → Applicability
→ Obligation Ledger → Target Discovery → Deterministic Generation
→ Code Validator → Primary Compose（必要时）→ Code Validator
→ Independent Review（必要时）→ DOCX → Claim Replay
→ Audit → Final Sweep → Coverage / Delivery Gate
```

四条硬不变量：

1. **代码负责可证明的部分**：地址、offset、span、数字来源、受保护字面量、DOCX 写入、claim replay、覆盖与交付门。
2. **模型不直接写 offset**：模型只返回 location / quote / replacement / reason；代码用 `resolve_quote`、`containing_segment`、`compact_offsets` 重新绑定。
3. **Validator 是硬门**：确定性生成、Primary Compose、Joint Compose 全部走同一套 `validate_edit`；Review 只能拒绝，不能绕过 Validator 直接覆盖文本。
4. **Repair 永远基于 ORIGINAL DOCX**：每个修复轮都从原始 `inspection` 重建 plan 与 artifact，不在错误 artifact 上叠加。

## 2. 模块

| 模块 | 职责 |
| --- | --- |
| `fundlex/models/config.py` | Primary / Review 两套独立 provider、model、base_url、key、超时、重试配置 |
| `fundlex/models/roles.py` | 任务→角色路由、独立调用记录、共享预算账本、按角色绑定 checkpoint |
| `fundlex/obligations.py` | Operation/Obligation IR、ALL_OF/ONE_OF/BRANCH/INDEPENDENT、Obligation Ledger、交付门投影 |
| `fundlex/applicability.py` | TRUE/FALSE/UNKNOWN；确定性 → Primary Judge → Review Arbitration；证据引文代码回查 |
| `fundlex/facts_recovery.py` | UNKNOWN/CONFLICT 事实聚焦重取、集合完整性证明、Review 仲裁 |
| `fundlex/targeting.py` | T3 Primary Locator（模型给 quote，代码绑定）；可选的无目标规则定位 |
| `fundlex/generation/validators.py` | 硬校验：必需项、边界、数字来源、受保护字面量、费用主题、组件×站点 |
| `fundlex/generation/components.py` | G16/G01/G03 的政策组件与字面证据 |
| `fundlex/generation/joint.py` | overlap 的 Joint Compose：整段输入、Validator、Review |
| `fundlex/generation/claim_replay.py` | 对已写入 DOCX 重放计划；文档级与段内边界证明 |
| `fundlex/recovery/` | FailureClass、RecoveryAction、预算、尝试历史、统一决策器 |
| `fundlex/delivery.py` | 用户层三态输出：完成 / 完成但有业务提示 / 部分无法可靠完成 |

## 3. Obligation IR 与 Ledger

每个 guide operation 获得稳定身份：

```text
G05:B1:O1   # 新身份（规则:分支:义务）
G05:0       # 旧 operation key，作为 alias 保留
```

- 同一条件下必须全部完成的 operation → `ALL_OF`；
- 同一 `new_text`、不同 `old_text` 的历史写法 → `ONE_OF`（G11/G12/G14）；
- 不同 condition → `BRANCH`；UNKNOWN 不执行任何分支；
- 无兄弟 operation → `INDEPENDENT`。

Ledger 在 target discovery **之前**创建。`applicability=TRUE` 且没有 target 时记录
`OPEN_OBLIGATION`，不会静默消失。Scope 模型遗漏某条规则（未返回该 rule_id）不是“不适用”：
`scope_map` 会用遗漏规则重试一次，仍遗漏则写入 `scope_gaps`，ledger 保持 `UNRESOLVED`。
Scope 明确返回空 section 列表才记录为 `scope_explicitly_empty`。

## 4. Facts / Applicability 恢复

```text
通用 Facts → 代码回查引文 → UNKNOWN/CONFLICT
→ 聚焦重取（class set + 枚举句完整性）→ 代码回查
→ Review 仲裁（带引文）→ 代码回查
→ 仍无法证明才保持 UNKNOWN/CONFLICT
```

- 类集合完整性：聚焦重取必须给出枚举句 `class_set_quote`；代码从枚举句解析类别标签，要求与候选集合**完全相等**，前缀句不能证明 C/D 存在。
- 仲裁只接受代码可回查的引文；不接受无引文的口头结论。
- Applicability 恢复得到的 TRUE/FALSE 写入 `Facts.condition_overrides`，planning
  的 `condition_status()`/`condition_matches()` 必须遵守该决定，不能再用旧 UNKNOWN 事实误判。

## 5. Generation / Validator / Review

| 层 | 内容 |
| --- | --- |
| T1 | 确定性模板（G14 集合删除、G09 splice、G08/G11 干净整句、G02/G04 类别替换） |
| T2 | 确定性 splice / 结构变换 / variant |
| T3 | Primary Compose（受约束整段替换） |
| T4 | UNRESOLVED（恢复预算耗尽） |

硬失败码至少包括：

```text
MISSING_REQUIRED_TERM
OUTSIDE_SPAN_CHANGED
UNAUTHORIZED_NUMBER
LOST_PROTECTED_LITERAL
UNEXPLAINED_HARD
COMPONENT_MISSING
TARGET_SOURCE_MISMATCH
STRUCTURE_UNSAFE
```

- 费用主题保护覆盖认购、申购、赎回、转换、销售服务、管理费、托管费；列表序号（如“4、”）不再被误当金额。
- G02/G04 只允许在目标段落的目标 span 内替换；claim replay 对**所有未授权段落**做文档级 diff=0 证明，并对目标段落做“按计划 span 重建后逐字相等”证明。
- G16 的四个机制组件（daily_accrual / direct_refund / non_direct_sales_policy / over_one_year_refund）必须在同一目标段落的输出中同时存在。
- Compose 与 Joint Compose 都必须先过 `validate_edit`，再由 Review Model 独立检查；Review PASS 不能绕过 Validator。

## 6. 双模型配置

最小配置（同型号也可，角色仍独立）：

```bash
LLM_PROVIDER=...
LLM_MODEL=...
LLM_BASE_URL=...
LLM_API_KEY=...
```

独立 Review：

```bash
FUNDLEX_PRIMARY_PROVIDER=openai
FUNDLEX_PRIMARY_MODEL=model-a
FUNDLEX_PRIMARY_BASE_URL=https://...
FUNDLEX_PRIMARY_API_KEY=...

FUNDLEX_REVIEW_PROVIDER=openai
FUNDLEX_REVIEW_MODEL=model-b
FUNDLEX_REVIEW_BASE_URL=https://...
FUNDLEX_REVIEW_API_KEY=...
```

或 JSON/YAML 角色文件：

```yaml
models:
  primary:
    provider: openai
    model: model-a
    base_url: https://...
    api_key_env: FUNDLEX_PRIMARY_API_KEY
  review:
    provider: openai
    model: model-b
    base_url: https://...
    api_key_env: FUNDLEX_REVIEW_API_KEY
task_roles:
  compose: primary
  compose_review: review
  audit: review
  sweep: review
  fact_arbitration: review
  applicability_arbitration: review
```

`FUNDLEX_MODEL_ROLES_FILE=/path/roles.yaml|json`。Review 只继承 Primary 的 endpoint
在**未单独配置**时发生；若 Review 配了不同 base_url 却没有自己的 key，启动会拒绝，
避免把 Primary 的凭据发给另一台主机。相同型号是明确允许的；报告中
`model.roles` 会分别显示 primary/review 的模型与调用数。

## 7. Recovery

FailureClass：`FACT / APPLICABILITY / TARGET / GENERATION / EXECUTION / VERIFICATION / INFRASTRUCTURE / RESOURCE`。

默认预算（`fundlex/recovery/policies.py`）：

```yaml
fact_primary_retry: 1
fact_review_arbitration: 1
applicability_review_arbitration: 1
target_deterministic_retry: 1
target_primary_locator: 1
generation_deterministic_retry: 1
generation_primary_compose: 2
generation_review_rounds: 2
joint_compose: 1
execution_rebuild: 1
artifact_recovery: 2
context_split: 2
infrastructure_pause_resume: 1
global_business_rounds: 3
```

覆盖：`FUNDLEX_RECOVERY_JSON` 或 `FUNDLEX_RECOVERY_<KEY>`。
完全相同的确定性重试会被拒绝；模型辅助重试必须带新的结构化反馈。
每次尝试写入 `RecoveryHistory`（动作、阶段、失败类、错误码、原因、结果、细节），
并进入报告 `recovery`、plan ledger 的 `recovery` 或 `fact_recovery_rounds`。

Claim Replay 失败时按失败类进入 `REGENERATE_ARTIFACT` / `REBUILD_PLAN`；重建后
重新 audit、重新 sweep、重新 replay，旧 artifact 的 verdict 不再复用。

## 8. 交付门

`delivery_status=complete` 仅当：

```text
Obligation Ledger 无 UNRESOLVED
+ 无 target/audit/sweep/claim/coverage unresolved
+ claim replay verified
+ qualification 未留下 fund_type 未核验的排除风险
```

用户层只看到：

1. 修改完成；
2. 修改完成，但有业务提示；
3. 部分修改无法可靠完成（规则、位置、业务原因）。

内部错误码仍保存在 `unresolved[].code`、`failure_class`、`recovery` 中，供调试与
corpus 评测使用。

## 9. 验证证据（2026-10-20，本地临时账本）

- 全量测试：`872 passed / 6 skipped`。
- 离线 validator shadow：`p6-dev-round14-12` 19 例 / 222 段编辑 / **0 hard FAIL**。
- 真实模型 D01（OpenCode Go，临时账本）：早期一版曾报 `complete_with_notices`
  （27 calls），但独立 Business Reviewer 复核 DOCX 后发现 G17 第二句仍留在 p760、
  G15 正文/摘要处理不一致，属于 **false_complete**。新增“delete-only 规则逐句残留在
  最终文档检测”与“重复条款副本一致性”硬门后，同一 D01 被如实阻塞为 partial
  （96 calls / 约 $0.052；claim replay 19 段 verified；audit 另发现 G09 第二处措辞缺失、
  G01 追加位置错误、G11 变体残留）。**该 false_complete 是本次改造最重要的验证发现。**
- D02（ETF 联接基金）：`eligible`、`fund_type=open_regular`，116 calls / $0.0615；
  G05 一处 compose 失败被如实标记 `RECALL_COMPOSE_FIXED_TEXT_MISSING`，交付 partial。
- D03：32 calls / $0.0222，G06 复合目标未解决，交付 partial。
- D11：99 calls / $0.0658，G15 目标误绑托管费条款、G09 第二处措辞缺失被 audit 抓住，
  交付 partial；此前旧版把该例报成 complete，属于 false_complete。
- 临时账本合计约 **963 requests / $0.5792**（未触碰生产账本）。
- **结论**：新架构已证明能发现旧版的 false_complete；尚未取得“最新硬门下真实合同
  complete”的验收样例。Final Architecture Reviewer 的 G05 satisfied-target 隐藏 delete、
  G11 ONE_OF 被新文误判残留两个 blocker 已修复并有回归测试（878 passed）。
- **生产发布（2026-10-20 20:37 CST，快照 `0fae88e`）**：`publish_workspace.sh` 成功，
  API/Worker active；关键模块与部署副本 sha256 一致；生产 `registry` + 输出上限 8000。
- **真实工作台端到端（通过）**：D01 经默认 `POST /api/tasks` → 上传 → seal → 真实 Worker/模型
  → 19 条修订（目录保留、14 页）→ 拒绝 1/接受 18 → `selected_final` 136125 bytes
  sha256 `efd9f20c…`，0 残留修订；`accept-all` 19 条成功；working 产物可下载；交付
  `incomplete` 如实。
- **子集回归（最终代码，未跑全量）**：D01 partial 93 calls/$0.0516，D02 partial 56/$0.0636，
  D11 partial 125/$0.0906，D16 partial 61/$0.0554；D11 旧版 false complete 被 blocked，
  D16 旧版 integrated complete 变 partial（需复核是否过度阻塞）。

## 10. 已知限制（未宣称完成）

1. **未取得最新硬门下的真实 complete，也未跑 514 全量 corpus（按用户指示由用户自行跑全量，agent 只跑子集）**。本轮真实合同
   暴露了 G09 部分替换、G01 错误站点、G06/G11 目标/变体残留等既有业务缺陷；全量需要
   约 3–4 万次模型调用、数十小时与约 $20–40，超出单次会话可执行范围。
   这不影响“新增硬门不会误拒既有好编辑”的离线证据，但不能替代 §51 的 514 验收。
2. **无目标规则的 T3 定位默认关闭**：`FUNDLEX_TARGET_LOCATOR_OPEN_RULES=1` 才启用。
   实测自动为无目标规则创建 locator 任务会把 G05 绑到相邻费率条款，风险高于收益；
   默认仍只对已存在但 quote 未解析的 target 使用 T3。
3. **Audit 的 context-limit 分批尚未实现**：inventory 与 scope 已分批；audit 仍先靠
   缩放窗口，极端长目标可能触发 `RECALL_AUDIT_CONTEXT_LIMIT`。
4. **G09/G15 的生成与定位仍有真实业务残留**：D11 的 G15 误绑托管费条款、D09/G09
   第二处措辞缺失，需要后续规则专项修复，不应靠放宽交付门掩盖。
5. **Review 与 Primary 允许同型号**（按用户方案 §4.2），独立的是任务、prompt、上下文与
   调用记录，不是模型权重；若生产要求“更强 Review”，需在 env 配置不同型号。
6. 前端尚未展示新的 `user_summary` / `failure_class` 字段；报告与 API 已带数据。

## 9. 2026-10-20 收口：operation-level Claim Replay、统一恢复、open obligation、occurrence-safe span

本轮不扩张架构，只补齐外部复查指出的四个缺口；所有 hard gate、UNKNOWN 不执行、OPEN obligation 不消失、Delivery Gate 语义保持不变。

### 9.1 Claim Replay：paragraph + operation/obligation 双层证明

- 段落层仍保留：artifact 段内结果必须等于“计划 edits 应用到原件”；目标段外 0 变化；正文/摘要重复副本一致性。
- 业务授权下沉到 operation unit：每个 edit（merged edit 拆到 component）按其 target 的 operation keys 建独立 `Authorization`；target 无 keys 时由该 unit 的 `old_text`/`new_text` 反推，绝不回退到同段 sibling 的 union。
- 每个 unit 独立跑同一个 `validate_edit`，输出 `rule_id / operation_id / obligation_id / target_id / location / authorized_span / source_text / expected_effect / actual_effect / validation`；`operations[]` 与 `obligations{}` 写入 replay 结果。
- 借用检测：append-only 操作吞掉既有文本 → `CLAIM_OPERATION_SPAN_UNAUTHORIZED`；替换段使用未选中 sibling 的 `new_text` → `CLAIM_OPERATION_EFFECT_MISSING`；带 occurrence 身份的 target 编辑了别的 occurrence → `CLAIM_OCCURRENCE_MISMATCH`。
- 同段 span overlap 不逐条 offset 重建，进入显式 Joint 验证：union 授权 + Validator 证明组合结果，同时逐 unit 复核各自新文本效果；任一项失败，整组 obligation FAIL。

### 9.2 Recovery：audit/repair 也走 RecoveryOrchestrator

- `RecoveryOrchestrator` 的 VERIFICATION 分支读取 `metadata.route_class`，按根因回到 TARGET/GENERATION/FACT/EXECUTION 候选动作；无根因证据的 VERIFICATION 不盲目重试，进入 UNRESOLVED。
- audit/repair 每轮把 issue 去重分类成 `RecoveryContext`（rule/target/obligation/failure_class/error_code/reason）并调用 `decide()`；未终局动作进入统一 `RecoveryHistory`，下一轮按 issue 数是否下降记录 `succeeded/failed`。报告保留 `recovery.business_rounds`，claim replay 的 artifact recovery 历史保留在顶层。
- `max_business_rounds` 仍是唯一全局断路器，不再承担具体 recovery policy。

### 9.3 Open obligation：代码先限制候选，再让模型定位

- `FUNDLEX_TARGET_LOCATOR_OPEN_RULES` 默认 `auto`：只对 applicable、无 target、scope 已映射的规则工作；候选段落由 topic tokens、class tokens、delete keyword bag、reference fragments 在 mapped section 内确定性筛出。
- 无候选 → 不调用模型，obligation 保持 OPEN；显式 `1/on` 仅用于调试旧的 section-first 行为；`0/off` 关闭。
- locator 只能看到候选段落；quote 必须唯一、location 必须在候选内、必须通过 topic/class/keyword 复核；越界、歧义、anchor 不符全部 rejected，保持 unresolved。
- 同一 quote 在正文/摘要重复出现时，为其他候选位置创建受控 duplicate-copy target，避免只改一处。

### 9.4 G02/G04：occurrence-safe span

- Target 新增 `site_candidates`、`occurrence_index`、`occurrence_anchor`。
- `resolve_occurrence()` 按 inventory quote 的局部上下文给每个相同 token 打分；唯一最高才绑定，否则抛 `RECALL_TARGET_OCCURRENCE_AMBIGUOUS`（TARGET），由 Recovery 决定是否定位；绝不默认第一个。
- Claim Replay 对带 occurrence 身份的 target 复核：编辑 span 必须覆盖授权 occurrence；编辑了同段另一个相同 token 会失败。

### 9.5 最终验证（2026-10-21）

- 全量 `pytest tests -q`：**929 passed / 6 skipped / 0 failed**。
- 真实模型子集（临时账本，最终代码）：D01 incomplete 79 calls/$0.0591；D02 incomplete 135/$0.0889；D11 incomplete 149/$0.0946；D16 incomplete 85/$0.0483。四例均保持 fail-closed partial，claim replay 能区分真实业务残留与未计划 sibling operation。
- 已知残余：重复正文/摘要副本（D01 p135、D16 p822）仍会因目标重叠或分歧阻塞；G06 composite、G15/G17 旧支付/用途句、G13/G14 残留仍是真实业务问题；sweep 修复尚未接入 RecoveryOrchestrator；AUDIT_NOT_COMPLETED（无根因 route）仍终局阻塞。

## 10. Operation Execution Closure（2026-10-21）

本轮不新增架构层，只把既有链路补齐为一条可追踪的 operation 闭包：

```text
Applicable Operation
  -> attributed Target (operation_keys)
  -> Planner (only selected operations)
  -> Final Edit Set (merge/conflict/joint compose)
  -> ledger reconciliation (planned only if final edit exists)
  -> DOCX Artifact
  -> per-obligation Claim Replay proof
```

关键约束：

1. `location target` 无 operation identity 时覆盖 0 个 operation，不再默认覆盖整条 rule；归因失败必须进入 OPEN/recovery，而不是计划整条规则。
2. `PlannedEdit` 自身携带 `operation_keys`/`obligation_ids`；Planner 只执行 target 归属的 operation。G05 的“调低…赎回费率”用有界 splice 保留中间修饰语，不靠整句 Compose。
3. Merge 的 alternative 只允许同一 `one_of_group`；同 rule 的独立 operation 重叠进入 Joint Compose/冲突，不再因“同 rule”被 covered。
4. Final plan ledger 从最终 edit set（含 component target ids）反推；`ledger=planned` 必须意味着该 operation 存在于 final edit set。
5. Claim Replay 检查全部 `applicability=TRUE` obligation，而不是只检查 `edited_rules`；replace/append/delete 分别要求 artifact 新效果、旧效果消失、`VERIFIED_ABSENT`；ONE_OF 只要求 source-present alternative 被处理。
6. Delivery 的 artifact proof 反过来可以关闭“未看到删除确认”的 sweep finding；但 exact residual 仍必须 block。
7. Recovery 增加 missing-operation target、no-progress snapshot、duplicate-copy repair；audit 只重审 dirty rules，并发受模型预算并发上限约束。duplicate-copy 克隆必须在初次 inventory、open-obligation recovery 和 missing-operation recovery 三个时点都执行；晚加入的 append target 若未复制到 body/summary 另一副本，最终仍会 `DUPLICATE_SITE_DIVERGED`。

当前真实子集仍是 **incomplete**：D01f 仅剩 G17 p760 残句；D02b 为 G16/P823；D11 为 G05:2/G16 + G22 audit；D16 为 p822/p1306 duplicate 与 G06 composite。上述结果之后的修复尚未全部重跑；详见 FL-D138。未发布生产，未跑 514。
