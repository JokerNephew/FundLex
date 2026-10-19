# FundLex 文本生成策略实施计划（v2：确定性优先、模型补位）

> **版本**：v2，2026-10-19。**v1 初稿已被本版取代**（v1 保留在 git 历史，差异见附录 B）。
> **来源**：产品负责人 2026-10-19 修订方案（主体）+ 同日评审修正点（附录 A，**待确认**）。
> **状态**：**待产品负责人批准后实施**。本文是架构与实施方案，**不代表代码已按此改造**。
> **关联条目**：FL-D104、FL-D106、FL-D118、FL-D119、FL-D120（见 `docs/DETAIL_ISSUES_AND_RESOLUTIONS.md`）。
> **不做的事**：不改指引内容、不并行改 scorer（见 §39.4 顺序）、不碰留出集、不在批次运行期间发布（FL-D096）。

---

# 1. 决策结论

FundLex 后续**不采用**"全量程序模板生成"，也**不采用**"所有修改均由模型生成、再由另一个模型检查"。统一升级为：

```text
规则 + Verified Facts
        │
        ▼
Policy Components
        │
        ▼
Strategy Router
   │        │        │
   ▼        ▼        ▼
Tier 1    Tier 2    Tier 3
模板生成  最小编辑   模型融合
   │        │        │
   └────────┴────────┘
            │
            ▼
Program Validators（V1 + V2）
            │
            ▼
Tier 3 additionally: Semantic Critic（V3）
            │
            ▼
Coverage Ledger
            │
            ▼
Delivery Gate
```

定位调整为：**Policy Compiler + Semantic Rewriter**。

- **Policy Compiler** 决定"必须改什么"；
- **程序生成器**负责可确定性生成的修改；
- **Semantic Rewriter** 只处理必须结合合同上下文重组语言的情况；
- **Validation / Coverage / Delivery** 负责**证明**修改正确，而不是让生成模型自行声明正确。

# 2. 核心目标

## 2.1 主目标

从"模型生成 + 代码事后验证"升级为"**程序生成优先 + 模型仅处理不可确定性生成的语义融合 + 所有修改留下可验证证据**"。

- 第一阶段目标：确定性产出占比 **≥70%**；稳定目标 **70%–80%**。
- 现状基线（`p6-dev-round14-05`）：284 条 edit 中纯程序来源 ≈183 条，**64.4%**。

本计划重点消除的不必要模型调用：

- G14 确定性集合删除却调用 compose；
- G09 短语替换却调用 compose；
- G15/G17 可直接删除却先 compose；
- G08/G11 干净场景本可模板实例化却走 compose；
- delete compose 失败后再走程序兜底的无效调用（14-05 实测 24 条）。

# 3. 不变量

## 3.1 政策不由模型决定

政策来源只能是 Guide + Verified Facts + 已裁定的产品规则。模型不得新增政策、费率、期限、份额类别，不得猜测基金属性或补全指引未提供的信息。

## 3.2 程序决定修改约束

每个 operation 必须**先**生成 Policy Components（`must_add` / `must_remove` / `must_preserve` / `parameters` / `authorized_spans` / `protected_literals`），再进入文本生成。

## 3.3 Facts 不可信时不得交给模型猜

Strategy Router 的硬边界，两类失败必须区分：

- **A. 文本结构前置条件失败**（无法安全 splice、段落结构复杂、跨 span 等）→ 允许 `Tier1 → Tier2 → Tier3` 降级；
- **B. 业务事实前置条件失败**（收费性质未验证、`class_count`/`service_group`/`fund_type` 不确定）→ **禁止降级到 Tier3 猜**，必须走 `Fact re-verification`：`VERIFIED → 继续生成`；`UNKNOWN / CONFLICT → unresolved`。

> **模型生成能力不能替代业务事实证据。**

## 3.4 修改必须可追溯

每条 edit 必须能回答：为什么改 / 依据哪条 operation / 基于哪些 facts / 改了哪个 source span / 用了哪个 tier / 哪些 validator 通过 / 最终 artifact 上如何证明成立。

## 3.5 Completion 必须是正向证明

不能再以"没有发现问题 ≈ complete"。要求：所有 applicable operation 都有明确 disposition；所有执行 edit 都有 artifact evidence；所有 validator requirement 满足；不存在 unresolved evidence。完成状态由 Coverage Ledger 推导。

# 4. 为什么必须采用混合生成策略

- 份额类别不止 A/C（D/E/F/Y/B/H），同字母含义因产品而异，"A→A/B、C→C/D"字面替换不可通用。真正应抽象的是 `subscription_fee_group` / `service_fee_group` / `direct_sales_free_group`，而不是具体字母。
- G15/G17 等删除型规则的 Guide `old_text` 与真实合同大量同义异构，不能依赖逐字匹配判适用性（实测 G15 逐字命中 1/514、G17 5/514）。
- 结论：**语义识别/定位可用模型；具体执行删除/生成必须尽量确定性。**

# 5. 核心数据模型

```python
@dataclass(frozen=True)
class PolicyComponents:
    operation_key: str
    must_add: tuple["ComponentRequirement", ...]
    must_remove: tuple["ComponentRequirement", ...]
    must_preserve: tuple["PreserveRequirement", ...]
    parameters: Mapping[str, Any]
    authorized_spans: tuple["SourceSpan", ...]
    protected_literals: tuple["ProtectedLiteral", ...]
    fact_dependencies: tuple[str, ...]
```

Component 不保存"一整段固定字符串"，而保存**结构化政策要素**：

```python
ComponentRequirement(
    id="direct_sales_fee_exemption",
    kind="fee_policy",
    properties={"channel": "direct", "classes": ["A", "D"],
                "fee": "subscription_fee", "charged": False},
)
```

即：**政策组件固定 ≠ 要求模型逐字复制模板**。

# 6. Strategy Router

统一三层：`tier1_template` / `tier2_minimal_splice` / `tier3_model_compose`。

Router 的单位不是 `rule_id`，而是 **`operation_key` + target/site + verified facts + 当前文本结构**——同一 G08 在不同合同里允许走不同 tier。

# 7. Tier 1：Deterministic Template / Structured Transform

适用：**结果可由 Rule + Verified Facts 唯一确定**。典型：固定 append、完整句模板实例化、集合删除、单词/短语替换、确定性 delete、slot 实例化。

## 7.1 G14（结构化集合删除）

原文 = 费率项集合（申购/赎回/转换/销售服务费率）。由 operation + Facts 得 `allowed`，执行 `remove = current − allowed` 的**最小删除 + 连接词修复**，而不是重写整句。

**Tier1 前置条件（全部满足才用）**：fee item 列举结构可完整解析；解析覆盖整个授权列表部分；不存在无法识别的费率项；无明显复合语义结构；applicable condition 已 VERIFIED。任一不满足 → Tier2/Tier3，**不得强行模板化**。（真实语料 G14 有数百种表达，含"已经含销售服务费""全部或者部分份额类别"等限定。）

## 7.2 G09

短语型修改优先 `variant table + fuzzy span resolve + minimal splice`（如 `扣除相应的费用 → 扣除或加上相应的费用`），不调用模型重写整句。

## 7.3 G15 / G17

**模型负责定位，程序负责删除。** 得到 source span 后优先 `target_span_delete` / `whole_paragraph_delete` / `composite_delete`，`composed_delete` 仅用于"目标 span 与必须保留内容不可安全分离"。

# 8. Tier 2：Minimal Splice

适用：政策修改确定性，但目标句混入大量不能修改的合同原有内容（G08/G11/部分 G14/复杂 replace）。

例：段落同时含 `申购费率 + 计算方法 + 赎回费率 + 收费方式……`，Guide 只授权改申购费率政策 → 找到授权 span、**只重写该 span**、其余原文保持不变。

# 9. Tier 3：Model Compose

Tier3 不是默认路径。仅当"已知道应变成什么业务含义，但无法确定性模板化或安全 splice 嵌入当前文本"时使用。

输入必须包含：`BEFORE / AUTHORIZED SPAN / POLICY COMPONENTS / VERIFIED FACTS / MUST ADD / MUST REMOVE / MUST PRESERVE / PROTECTED LITERALS`。

模型**不得重新判断**：规则是否适用、政策应该是什么、基金属于哪类——这些必须由前序阶段确定。

# 10. G16 作为首个 Tier3 试点

真实合同的销售服务费支付机制表达差异极大（托管人自动支付 / 管理人发指令 / 登记机构代收 / 管理人代收 / 月初 5 个工作日 / 次月前 5 个工作日 / 不同支付路径），不能整段覆盖。建议：

```text
must_add:     daily_accrual, direct_refund, non_direct_sales_policy, over_one_year_refund
must_preserve: fee_rate_formula, existing_payment_actor, existing_payment_path, existing_payment_timing
```

`must_preserve` 分两类：**deterministic preserve**（`0.40%`、`5个工作日`、`注册登记机构` 等可 exact/protected literal 校验）；**semantic preserve**（支付责任链、主体关系、复杂计算机制，无法结构化时交 V3 辅助判断）。

# 11. V1 —— Policy / Literal Validator

判断政策组件是否落实、是否引入无法追溯的硬事实：

- **Policy Components**：`must_add` 全部满足；`must_remove` 全部消失；required class groups 覆盖；禁止出现的 component 不存在。
- **Number Provenance**：replacement 中所有新数字必须来自 Guide / Verified Facts / Source text / 显式规则常量，否则 `UNAUTHORIZED_NUMBER`。
- **Protected literals**：百分比、日期、工作日、数量、明确主体名称、公式变量、关键定义词。

# 12. V2 —— Authorized Change Validator（最重要的程序安全门之一）

## 12.1 授权单位 = SourceSpan

```python
SourceSpan(location="p236", start=18, end=47, source_sha256="...")
```

## 12.2 授权窗口外原则

> **授权 span 外的源文本必须保持精确一致。**

`compact / 去空白` 只允许用于目标匹配、diagnostic、兼容性分析，**不能单独作为 V2 PASS 条件**；`exact outside-span unchanged` 优先于 `compact unchanged`，避免标点/空格/定义词变化或被重新组织却因去空白后接近而被误判安全。

## 12.3 V2 输出（示例）

```json
{"verdict": "FAIL",
 "violations": [{"code": "UNAUTHORIZED_TEXT", "location": "p236",
                 "before": "...", "after": "..."}]}
```

错误码族：`UNAUTHORIZED_NUMBER`、`LOST_PROTECTED_LITERAL`、`UNAUTHORIZED_SUBJECT_CHANGE`、`UNAUTHORIZED_TERM_CHANGE`、`OUTSIDE_SPAN_CHANGED`。

# 13. V3 —— Independent Semantic Critic

**仅强制用于 Tier3。** Tier1/Tier2 默认不调用（避免"为减少生成模型调用，却给每条确定性 edit 又加一次模型复核"）。

## 13.1 V3 只判断代码难以证明的问题

① 改写后业务含义是否落实 Policy Components；② 是否改变原文未授权的业务含义；③ semantic `must_preserve` 是否丢失；④ 是否形成内部矛盾；⑤ 是否存在程序无法识别的政策遗漏。

## 13.2 V3 不负责

不重复判断：百分比是否变、数字有无来源、窗口外是否变化、类别列表是否缺字母——**这些属于 V1/V2**。

## 13.3 同模型与异模型

默认允许生成模型 = 验证模型，但必须：**独立请求、独立 prompt、只读 BEFORE/AFTER/policy evidence、不得看到 generator reasoning**。Evidence 记录：

```json
{"generator_model": "...", "verifier_model": "...",
 "verification_independence": "same_model_separate_call"}
```

后续可配 `cross_model`，但**不得把"异模型"当作正确性的唯一来源**。

# 14. V3 FAIL 的最终处置

取消"标记存疑照交"。规则：

```text
V3 PASS → 正常进入 artifact verification
V3 FAIL → 允许 regeneration 1 次
第二次仍 FAIL → operation = unresolved
```

可以生成 **working artifact** 供人工查看，但 **final-complete = 禁止**：
> 可以让用户看到结果，不能声称合同已完成全部修改。

# 15. Validation Verdict

统一 `PASS / FAIL / UNKNOWN` 三态——模型异常、证据缺失、解析失败与实际验证失败不是同一种状态，禁止只有 `true/false`。

# 16. Generation Evidence（进入 Coverage Ledger，不建平行状态）

所有 Generation Evidence 直接进入 **Coverage Ledger**，避免 generation/audit/sweep/delivery 各自维护不同真相。示例：

```json
{"ruleId": "G16", "operationId": "G16:0", "siteId": "site-72fa",
 "generation": {"requestedTier": "tier2", "actualTier": "tier3",
                "fallbackReason": "complex_mixed_clause",
                "policyComponents": {"mustAdd": ["daily_accrual", "direct_refund", "over_one_year_refund"],
                                     "mustRemove": [],
                                     "mustPreserve": ["fee_rate_formula", "payment_path"]}},
 "validation": {"v1": {"verdict": "pass"}, "v2": {"verdict": "pass"},
                "v3": {"verdict": "pass", "model": "..."}},
 "artifactEvidence": {"verified": true},
 "state": "ARTIFACT_VERIFIED"}
```

Delivery Gate 只读取 Coverage Ledger。

# 17. Strategy Registry

新增 `fundlex/generation.py`：

```python
@dataclass(frozen=True)
class StrategySpec:
    default_tier: str
    allowed_tiers: tuple[str, ...]
    required_fact_status: tuple[str, ...]
    required_components: tuple[str, ...]
    preserve_policy: tuple[str, ...]
    mode: str
```

索引按 **`operation_key`**（`G14:0`、`G16:0`），不是只按规则号。

# 18. Router 决策规则

```text
Facts Evidence ──不足──→ fact verification / unresolved
        │
        ▼
    Operation → Target Structure
        ├─ 可唯一生成 → Tier1
        ├─ 可局部 splice → Tier2
        └─ 必须语义融合 → Tier3
```

> **UNKNOWN FACT ≠ Tier3。**

# 19. G08 / G11 参数化原则

核心语义模型不用 `A类/C类`，用：

```text
subscription_fee_group / service_fee_group / direct_sales_exempt_group / other_sales_charged_group
```

例：`{"subscription_fee_group": ["A","D"], "service_fee_group": ["C"], "direct_sales_exempt_group": ["A","D"]}`，正文由程序实例化。

- **19.1 干净整句**（独立、无其他费率政策/计算方法/公告义务/赎回政策）→ **Tier1 template**；
- **19.2 混合句**（同段还有赎回费率、计算方法、收费方式、公告义务）→ **Tier2 splice**，不得整段替换；
- **19.3 无法安全 splice**（语义交织、跨句依赖）→ **Tier3 compose**。

# 20. 缺失类别组

如 `A + Y` 而没有 service fee group：**不得生成"C 类基金份额不收取申购费用"这类不存在的类别**。

原则：**不存在的业务组不得为了满足 Guide 模板而凭空生成**。对应 component 若 `group = empty → drop component`，且必须留下 **`component_not_applicable`** evidence，不能只是静默删除一句。

# 21. Phase 0 —— 基线冻结

实施任何行为改变前：① 固定当前代码 commit；② 固定 Guide hash；③ 固定 scorer；④ 固定最新已完成开发集结果；⑤ 保存 completion rate / actual-reported completion matrix / edit source mix / calls / cost / failure distribution。

若实施前已有更新的**完整有效**批次（如 `round14-08` 若有效）→ 用其作主基线；否则 **主基线 = `round14-05`**（220/236、0.9322、1240 calls、$0.9053，保留为历史对照）。注意供应商混杂（14-05 = DeepSeek；当前头部 commit `03fbbfa` = OpenCodeGo），对照报告须注明。

# 22. Phase 1 —— Registry + Telemetry（**不改生成行为**）

新增 `fundlex/generation.py`：Strategy Registry、tier decision、fallback reason、generation telemetry。新增 `tools/evaluation/generation_mix.py`（必须复现现有 generation mix）。

验收：**Behavior diff = 0、Output diff = 0、现有评估结果不变**（度量方式：策略默认惰性路径 + 单测 + 小批对照，见附录 A-7）。

# 23. Phase 2 —— Validator Shadow Mode

先构建 V1/V2，但**只观测、不阻断**；对既有 round artifact 离线重放。必须统计：V1/V2 failure rate、false positive samples、rule distribution、tier distribution。**FL-D119 主题错配必须能够被新 validator 捕获**。人工检查确认误报可控后，才启用 blocking。

# 24. Phase 3 —— Tier1 上线

第一批：**G14、G09、G15/G17 deterministic delete pre-route**（输入输出边界清晰、可验证、风险低于语义 compose、可明显减少调用）。

验收：G14/G09/delete 的 compose 显著下降；**correct completion 不下降；false complete 不增加；结构破坏 = 0**。

# 25. Phase 4 —— Tier2 G08 / G11

接入参数化模板 + minimal splice，重点验证：A/C/D/E/F/Y 类别组合、无 service group、同段附带赎回内容/公告/多个费用主题——必须覆盖 B 类报告已发现的复杂形态。

# 26. Phase 5 —— Tier3 + V3

最后才改 `compose_variant`。对 FL-D106 两条限制**不是简单取消，而是升级**：

```text
RECALL_COMPOSE_FIXED_TEXT_MISSING / RECALL_COMPOSE_NEW_NUMBERS
        →
Policy Component check + Number provenance + Authorized diff + Semantic critic
```

# 27. Phase 6 —— G16 Pilot

G16 做首个完整 Tier3 验证规则，要求闭环：`Policy Components → Compose → V1 → V2 → V3 → Artifact verification → Coverage Ledger`。

若 G16 Pilot 不能稳定通过：**暂停扩大 Tier3**，而不是继续迁移更多规则。

# 28. Phase 7 —— Evaluation & Freeze

### Unit / Integration
`pytest tests -q`，0 unexpected failures。

### Mutation Tests（新增 Completion Mutation Suite）
对正确产物故意制造：① 删除 must_add 一句；② 重插 must_remove；③ 修改 0.40%；④ 修改 5 个工作日；⑤ 删除 direct refund；⑥ 改错份额类别；⑦ 删除一半跨段内容；⑧ 修改未授权公告义务；⑨ 重复 append；⑩ 修改 payment actor。要求 **Delivery Gate 必须拒绝 complete**。

### Development Set
至少跑完整开发集，比较：target completion、contract completion、false complete、false incomplete、calls、cost、generation mix、validator failures。

# 29. Completion Gate 混淆矩阵（一级指标）

| 系统判断 | 实际完成 | 分类 |
| --- | --- | --- |
| complete | complete | TP |
| complete | incomplete | **FP / false complete** |
| incomplete | complete | FN |
| incomplete | incomplete | TN |

优先级：**① FP → 0；② 保持正确 target completion；③ 降低 FN；④ 降低模型成本。** 不能为了 70% deterministic 牺牲 false complete。

# 30. 成本指标（三分）

`Tier3 每次 compose +1 verify` 与"总调用不增加"存在天然冲突，拆为：

1. **Generation Calls**：目标显著下降（G09/G14/delete/G08/G11 减少 compose）；
2. **Verification Calls**：只统计 Tier3 V3，允许新增；
3. **Total Calls**：生产验收要求不得明显高于基线，最终目标 `≤ baseline`。Shadow/Pilot 阶段允许暂时 `+10%`，但必须记录原因；超过后不得自动扩大 rollout。

# 31. V3 调用预算

V3 只调用 `actual tier == tier3`（不是每 operation 一次）。默认 `1 compose + 1 verify`；失败最多 `1 次 regenerate + 1 次 verify`。单 operation 最大 **4 次模型调用**，超出 → `unresolved`。**禁止无限 repair loop。**

# 32. 报告结构

`report.json` 增加：

```json
{"generation": {"tier1": 123, "tier2": 54, "tier3": 31,
                "fallbacks": {"tier1_to_tier2": 7, "tier2_to_tier3": 5},
                "validators": {"v1_fail": 1, "v2_fail": 2, "v3_fail": 1},
                "model_calls": {"generation": 31, "verification": 31, "regeneration": 2}}}
```

每条 operation 保存详细 evidence（见 §16）。

# 33. Frontend / 用户状态

Tier3 两次复核仍失败：前端不得显示"修改完成"，应显示"**修改结果已生成，但存在未解决项**"，列出 Rule / Operation / Location / Reason / Validation failure；working DOCX 可下载检查，但 **complete = false**。

# 34. 灰度开关

`FUNDLEX_GENERATION_STRATEGY = legacy | registry_shadow | registry`；细粒度 `FUNDLEX_GENERATION_TIER1/2/3`；必要时按 operation 的 `enabled_operations` 控制 rollout。

# 35. 回滚原则

每阶段：独立 commit、独立测试、独立评估、可单独 revert。**禁止**一个 commit 同时做"重构 recall.py + 改生成策略 + 改 scorer + 改 Guide"；行为改造与机械重构必须分离。

# 36. 与 Recall 重构的关系

不要求先完成整个 Recall 架构重构，但新增代码直接按未来结构：

```text
fundlex/generation/
    types.py  policy_components.py  router.py
    template.py  splice.py  compose.py  validators.py  evidence.py
```

不继续把所有逻辑塞进 `recall.py` / `recall_pipeline.py`。

# 37. 推荐实施 Commit 顺序（7 个行为清晰的 commit）

1. generation types + registry + telemetry（不改行为）
2. policy components + V1/V2 shadow validators（不阻断）
3. tier1：G14 + G09
4. deterministic delete routing：G15 / G17
5. tier2：G08 / G11
6. tier3：V3 + compose validation
7. G16 pilot + completion integration + evaluation

之后另行决定是否迁移其他 operations。

# 38. 指标

| 类别 | 指标 | 最终要求 |
| --- | --- | ---: |
| Correctness | 开发集 target completion | 不低于冻结基线 |
| Safety | false complete | **0** |
| Safety | DOCX 结构破坏 | **0** |
| Generation | 确定性产出占比 | ≥70%，目标 80% |
| Cost | generation model calls | 显著下降 |
| Cost | total model calls | 稳态不高于基线 |
| Validation | Tier3 V1/V2/V3 evidence | 100% |
| Coverage | applicable operation disposition | 100% |
| Traceability | edit → operation → evidence | 100% |

# 39. 仍需产品裁定的业务问题

## 39.1 无 service group 的产品（如 A+Y）
建议：不生成不存在类别的固定句，仅对真实存在的收费组实例化；Evidence 记 `component_not_applicable`。

## 39.2 "按收费性质"适用范围
需最终确认是否从 G08 扩展到 G11/G14/G16 及其他规则。技术架构应支持，但不提前把业务结论写死。

## 39.3 同义满足
如"每日计算、逐日累计"是否等价于"每日计提"——属产品/业务语义裁定。**裁定前不得让生成模型自行决定并形成永久规则。**

## 39.4 评分口径
新生成方式允许"业务含义满足但非逐字等于 Guide new_text"。正确顺序：**先冻结 scorer → 测真实影响 → 单独裁定 scorer 是否升级**。不能为了让新方案分数更高而同时修改 scorer。

# 40. 最终验收标准

- **A. Generation**：确定性 generation ≥ 70%；
- **B. Correctness**：target completion 不低于冻结基线；
- **C. Safety**：false complete = 0、DOCX structure failure = 0；
- **D. Evidence**：所有 Tier3 edit 满足 `V1 PASS + V2 PASS + V3 PASS + artifact verification PASS`；
- **E. Coverage**：所有 applicable operation 为 `SATISFIED / ARTIFACT_VERIFIED / ALREADY_SATISFIED / NOT_APPLICABLE / UNRESOLVED` 之一；**不得存在 UNKNOWN 却宣布 complete**；
- **F. Cost**：完成率稳定后，总模型调用不高于冻结基线。若准确率显著提升但成本略增，必须单独由产品负责人批准，不自动视为通过。

# 41. 最终原则

```text
能算出来的，不让模型写。
能局部改的，不让模型重写整段。
必须由模型融合的，先把政策和事实固定下来再让模型写。
模型写出来的，不由模型自己决定是否安全。
程序能够证明的，一律程序证明。
程序无法证明的，模型只能提供语义证据，不能越过 Delivery Gate。
事实不确定时，不生成。
验证失败时，可以输出 working result，但不能宣称 complete。
```

最终数据流：

```text
Guide
  │
Verified Facts
  │
  ▼
Policy Components
  │
  ▼
Strategy Router
  ├──────────────┬────────────────┐
  ▼              ▼                ▼
Tier1           Tier2            Tier3
Template        Splice           Compose
  │              │                │
  │              │              V3 Critic
  └──────────────┴────────────────┘
                 │
                 ▼
               V1 + V2
                 │
                 ▼
          Artifact Verification
                 │
                 ▼
            Coverage Ledger
                 │
                 ▼
            Delivery Gate
```

> **FundLex 不追求"模型把合同改得像人写的一样"。**
> 真正目标：**在保留合同原有内容的前提下，以尽可能确定性的方式落实政策修改；只有确定性方法无法安全表达时才使用模型，并且每一次模型修改都必须形成可验证证据。**

---

# 附录 A：评审修正点（2026-10-19 提交，**待产品负责人确认**）

以下为技术评审发现、建议修正/澄清点；确认后并入正文对应阶段。

1. **§12 V2 与 §9 Tier3 的"授权窗口"张力（最重要）**：Tier3 进场的原因正是"窗口划不干净"；若授权窗口无法精确映射回目标 span，V2 的"窗口外精确一致"在 span 内部就提供不了保护。建议补一条 **"变更解释 diff"**：无法划窗时，span 内每一处变化必须能被某个 `must_add` / `must_remove` 组件或已声明授权短语模式**解释**，解释不了的变化 → `UNAUTHORIZED`，交 V3 复核；窗口可划时仍按 §12 精确检查。
2. **V2 分两层实现**：① 整篇级——edit span 外精确一致（对现有拼接器是"by construction"，保留作 writer 回归哨兵）；② span 内授权窗口级（真正的门）。避免把天然成立的事项当门而产生误报。
3. **§16"单一 Coverage Ledger"的迁移路径**：现状有 edits/audit/sweep/delivery 四套状态。建议 Phase 1 先交付**只读合并视图 + 状态映射表**（`planned/completed/satisfied/out_of_scope` ↔ audit verdict ↔ sweep finding → 五个终态），存储层统一放后期，避免一次性大重构。
4. **§19 需要 Facts 扩展**：`direct_sales_exempt_group` / `other_sales_charged_group` 目前**不存在于 Facts**（现仅有 classes 的 `subscription_fee`/`service_fee`）。需走 Facts 抽取+核验流程（含 prompt/schema/核验），并注意与 FL-D114（未核验 facts 的参与边界）的连带关系——§3.3 实质上会让"未核实事实不得参与分支"落地，请一并确认。
5. **FL-D119 修复应显式列入计划**：V2/V3 只能把主题误配拦成 unresolved（交不出去），而根因修复（survey 模糊阈值对"申/赎"一字之差放行 + satisfied 尾句误触发）能直接把它变正确。建议并入 Phase 2/3，并把 `D01/p227` 样本保留为常驻回归例。
6. **§28 变异测试要对准"Artifact Verification"的实际机制**：需把 artifact verification 从"哈希校验"升级为"**claims vs artifact 重放**"（复用 `_finding_evidence` 的确定性证据），否则变异项 ①②③④⑩ 不保证被 Gate 拒绝。建议列入 Phase 7 前置。
7. **§22 验收的度量方式**：'Output diff = 0' 需定义操作口径（代码路径惰性证明 + 单测 + 一个小批对照），否则无法验收。
8. **小项**：① §31 的 4-call 上限与 §14 的 1 次 regeneration 自洽（1 compose + 1 verify + 1 regen + 1 verify）；② V3 evidence 建议记录 prompt_version 与独立性标记（trace 层已有基础）；③ §30 Shadow 阶段 +10% 需在批次说明中预登记原因。

# 附录 B：与 v1 草稿（2026-10-19 初版）的差异

- v1 的"V3 失败 → 标记存疑照交"被本版 **§14 推翻**（改为 unresolved、禁止 complete）；
- v1 的"缺组/主题守卫等交 compose 层模型复核"被本版收敛为 **§12 V2（程序门）+ §11 V1（组件/数字/字面）**；
- v1 的"tier 前置条件不满足统一降级 tier3"被本版 **§3.3 拆分为两类失败**（事实失败不得猜）；
- 本版新增：§14/§16/§29/§30/§31/§37/§40 等（V3 处置、单一 Ledger、混淆矩阵、成本三分、调用预算、commit 顺序、最终验收）。
- 相关条目：FL-D106（2026-10-19 裁定：compose 两条硬约束由本章程替代）、FL-D104（G08-1/G08-2 口径）、FL-D119（回归样本）、FL-D120（方案总记录）。
