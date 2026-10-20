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

- 全量测试：`860 passed / 6 skipped`。
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
  complete”的验收样例。

## 10. 已知限制（未宣称完成）

1. **未取得最新硬门下的真实 complete，也未跑 514 全量 corpus**。本轮真实合同
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
