# 文本生成策略实施计划：确定性优先、模型补位（2026-10-19）

> **来源**：FL-D120（产品负责人方案 + 同日评估，见 `docs/DETAIL_ISSUES_AND_RESOLUTIONS.md`）。
> **状态**：**待产品负责人批准**。本文是实施计划，**不代表已实施**；各阶段完成后再按项目惯例更新为"已实施 / 已验证"。
> **关联条目**：FL-D106（模型判、代码兜硬事实；2026-10-19 裁定 compose 两条硬约束可推翻）、FL-D104（G08-1/G08-2 口径）、FL-D119（主题误配，本计划 V2 的回归样本）、FL-D118（供应商阻塞）。
> **不做的事**：不改指引内容、不改评分口径（未裁定前）、不碰留出集、不在批次运行期间发布（FL-D096）。

---

## 1. 目标

把引擎从"模型生成 + 代码验证"升级为：

```text
程序生成优先
+ 模型只做不可模板化的语义融合
+ 模型生成后必须经过「程序硬校验 / 授权 diff / 独立模型复核」三层验证
```

- **主目标**：确定性产出占比从现状 **56%–64%** 提升到 **70%–80%**；
- **约束**：开发集目标完成率不降低（基线 `p6-dev-round14-05` = 220/236 = 0.9322），`kept`/漏改不增加，结构破坏 = 0；
- **定位语**：FundLex = **Policy Compiler + Semantic Rewriter**。

## 2. 三不变量（不因本计划改变）

1. **政策来源仍是指引 + 已验证 Facts**——模型不发明政策、不发明数字；
2. **程序决定"改什么、必须包含什么、哪些内容不能丢"**（Policy Components 由规则与事实推导）；
3. **一切产出可追溯、可回退**；结构安全；删除不截半句。

"政策文字逐字"的含义按 FL-D106 2026-10-19 裁定升级为：

```text
授权窗口之外（去空白后）逐字不变
+ 授权窗口之内 组件校验（must_add / must_preserve）
+ 独立模型复核记录
```

## 3. 目标架构（四层）

```text
Guide Operation（改什么：op / old_text / new_text / condition）
      │
      ▼
① Policy Components（程序推导，逐操作生成）
   must_add / must_remove / must_preserve / parameters
      │
      ▼
② Strategy Router（运行时前置条件决定层级，不按规则静态归类）
   tier1 template        —— 结果可由 规则+Facts 唯一算出（程序生成）
   tier2 minimal-splice  —— 只动授权句段、其余逐字保留（程序最小编辑）
   tier3 model_compose   —— 需结合合同原文重组语言（模型生成）
      │  级联顺序：tier1 → tier2 → tier3（前置条件不满足则降级，默认安全侧 = tier3）
      ▼
③ Three-layer Validator
   V1 程序硬校验：must_add 组件齐全、类别覆盖、protected literals、数字来源可溯
   V2 授权 diff：授权窗口外 compact 逐字不变；未授权类变化（数字/百分比/期限/主体/公式/公告条件）直接拒绝
   V3 独立模型复核：semantic critic（只回答代码判不了的问题；不作为最终安全门）
      │
      ▼
④ Evidence & Delivery：每条编辑记录 tier / validators / verify verdict；报告新增 generation 段
```

## 4. 现状基线与差距

### 4.1 数据基线（`var/recall-first-evaluation/p6-dev-round14-05/`，20 例共 284 条编辑）

| 产物来源（content_source） | 条数 | 占比 |
| --- | ---: | ---: |
| 纯程序路径（fragment_replace 89、guide_text 31、whole_paragraph_delete 24、composite_delete 11、fragment_delete 10、variant_delete 10、variant_replace 5、target_span_delete 3） | 183 | **64.4%** |
| composed（含 model 组合） | 53 | 18.7% |
| merged（机械合并，组件来源混合） | 30 | 10.6% |
| composed_delete（模型 delete 组合） | 18 | 6.3% |

> 口径说明：`whole_paragraph_delete` 的文字由程序产出，但其中 24 条是**先发起 compose（失败 `DELETE_NOT_SHRINKING`）再走确定性兜底**——Phase 2 应前置判断直接走确定性，以省调用。

### 4.2 规则级差距（同批次）

| 规则 | 现状 | 差距 |
| --- | --- | --- |
| **G14** | 16/16 全 composed | 属第一类（集合删除），应改 tier1 |
| **G09** | 13/13 全 composed | 属短语级改写，应改 tier1/tier2 |
| G08 | 7 composed / 7 fragment | 混合；需前置条件分流（干净整句→模板；范围大段→splice/compose） |
| G11 | 4 composed / 9 fragment | 同上 |
| G15 / G17 | 已基本"模型定位 + 程序删除"（59 条中 43 条确定性路径） | 仅剩 composed_delete 16 条可降 |
| G16 | append 固定句 + 合并（guide_text 7 + merged 15） | **无「与合同原机制融合 + 保留」机制**，tier3 试点 |
| G05 | 已基本确定性（fragment 29） | 无需改动 |

### 4.3 已有可复用机制（避免重复建设）

- **模板/实例化**：`instantiate_slots`、`class_label`、`_append_without_missing_group`（缺组丢弃同原则）；
- **最小编辑**：`_splice_fragment`、`variant_delete`/`variant_replace`、`target_span_delete`、`whole_paragraph_delete`、`composite_*`；
- **已有校验**：`_component_ok`（内容接线）、`RECALL_COMPOSE_FIXED_TEXT_MISSING`、`RECALL_COMPOSE_NEW_NUMBERS`、preserved 回查、merge 覆盖判定；
- **模型 critic**：audit 阶段（只标记不回撤）、sweep 复核。

## 5. 分阶段实施

> 每阶段独立 commit、可 revert；不带着失败测试发布；批次运行期间禁止发布。

### Phase 0 —— 策略注册表 + 遥测（**不改任何行为**）

- 新增 `fundlex/generation.py`：
  - `StrategySpec(default_tier, preconditions, required_components, preserve, mode)`；
  - `STRATEGY_REGISTRY` 按 `operation_key`（`G14:0` 形式，已有）索引；未登记项**默认 tier3**（安全侧）；
  - 注：策略放代码侧而非 guide JSON——guide 是编译产物，手工字段重编会丢。
- 报告扩展：edit evidence 增加 `strategy/tier/validators`；报告新增 `generation` 汇总段（向后兼容）。
- 新增分析工具 `tools/evaluation/generation_mix.py`：从既有 `report.json` 复算确定性占比（按规则/按 tier）。
- 测试：`tests/test_generation_registry.py`（22 条规则全覆盖断言、未登记回退 tier3、schema 兼容）。
- **验收**：行为零变化；工具复现 4.1 的数字。
- **回滚**：纯新增，revert 即可。

### Phase 1 —— 三层验证器（先**旁路观测**，不拦截）

- V1（程序硬校验，`fundlex/` 新增校验模块）：
  - `required_components_present(rule, facts, replacement)`：类别覆盖（`subscription_group`/`service_group` 全部出现）、must_add 句齐全、缺组丢弃一致性；
  - `protected_literals(before, after)`：数字/百分比/期限/主体/公式行的保护集，来源 = 原句 + Facts + 指引文本。
- V2（授权 diff）：
  - `authorized_change_diff(before, after, operation, facts)`：推导授权窗口（replace 的 old→new 差异句段、delete 的目标 span、append 的插入点），**窗口外 compact 逐字不变**；未授权类变化分类报告（`UNAUTHORIZED_NUMBER`/`UNAUTHORIZED_TEXT`/`LOST_PROTECTED_*`）。
  - 设计要点：这一条门与 `_splice_fragment` 语义同源，可覆盖数字/期限/公式/公告条件的绝大部分。
- 接线：**只写报告与 soft 码**（如 `VALIDATOR_*`），不改交付判定。
- 离线回放：对 round14-05 的既有 edits 复算命中率（零模型成本）；**FL-D119 的 D01 样本必须被 V2 命中**（回归样例）。
- 测试：正/反例（0.40% 保留、数字新增、主题错配）。
- **验收**：FL-D119 样本被拦；误报率在 20 例上完成度量并记录。
- **回滚**：观测模式，revert。

### Phase 2 —— tier1 模板生成器（G14 优先，G09 其次）

- **G14 结构化集合删除**：
  - 解析原句费率项集合（申购费率/赎回费率/转换费率/销售服务费率；分隔符 `、`/`和`/`以及`/`与`）；
  - `allowed` 由规则条件推导：`class_count=1` → {申购费率}；`class_count=multiple` → {申购费率, 销售服务费率}；
  - 对 `current − allowed` 做**最小删除 + 连接词归一**，其余原样保留；
  - 前置条件：目标 span 可解析为单句且费率项集合完整，否则降级 tier2/3。
- **G09 短语级 splice**：`扣除相应的费用` → `扣除或加上相应的费用` 等变体表 + 句边界吸附（复用 `fuzzy_span_clause`）。
- 落地门：产物须过 V1/V2（Phase 1）；ledger 记录实际 tier。
- **验收**：G14/G09 编辑不再走 compose；整体确定性占比 ≥70%；（离线）无新增 kept。
- **回滚**：按规则灰度开关（`FUNDLEX_GENERATION_STRATEGY=registry|legacy`）。

### Phase 3 —— tier2 参数化模板收口（G08 / G11）

- 前置条件分流（**不按规则静态归类**）：
  - 目标 span = 独立干净整句、无多余内容 → 直接实例化模板（`instantiate_slots`，已存在）；
  - span 含未授权内容（赎回费率、计算方法、公告义务、收费方式等，即 B 报告"范围大于指引"形态）→ **只对授权句段做最小编辑**，余文逐字保留；
  - 两者都不满足 → tier3。
- 缺服务组产品（A+Y 等）：按 FL-D104 口径做"变通"= **丢弃命名缺失组的固定句**（与 `_append_without_missing_group` 同原则），其余照改；具体写法见第 9 节待裁项。
- 直销豁免组：由 Facts 推导（收费组 ∩ 合同已载明直销豁免的类别）。
- **验收**：G08/G11 的 composed 占比下降；FL-D119 类主题错配在 V2 被拦。
- **回滚**：按规则灰度。

### Phase 4 —— tier3 接线：compose + 三层验证（落实 FL-D106 2026-10-19 裁定）

- `compose_variant`：两条硬约束降级——`RECALL_COMPOSE_FIXED_TEXT_MISSING` 的固定文本改为 V1 的必须组件输入；`RECALL_COMPOSE_NEW_NUMBERS` 改为 V1 数字溯源校验（不再硬拒）；
- `_component_ok` 的 `composed` 分支：改为要求 **V1+V2 通过证据 + V3 复核记录**；
- 新增 V3 独立复核调用（`recall_verify`）：
  - 默认**同一模型独立调用**（独立提示、独立上下文）；预留 `FUNDLEX_VERIFY_MODEL`（异模型）配置；
  - 复核清单：① 语义一致（允许措辞变化）② 不新增未授权数字/费率/承诺 ③ 不遗漏要点 ④ 保留件未丢；输出 verdict + basis + 引文；
  - 不通过：重试 1 次 → 仍不过的处置见第 9 节待裁项。
- **G16 融合试点**（tier3 首个用例）：
  - required_components：`daily_accrual`、`direct_refund`、`non_direct_monthly_payment`、`over_one_year_refund`；
  - preserve：费率公式、既有支付路径/主体/时限。
- 预算与观测：compose 上限 = `max(8, 规则数)` = 22/合同；每次 compose **+1 次复核调用**；记录每合同 compose/verify 调用数与失败码分布。
- **验收**：`RECALL_COMPOSE_*` 失败率下降；kept / false_complete 不上升；调用与成本相对 round14-05 不劣化。
- **回滚**：`FUNDLEX_GENERATION_STRATEGY=legacy` 整体回退。

### Phase 5 —— 回归与冻结

- 全量 `pytest tests -q`（对照既有 690+ 基线）；
- 离线回放（既有报告 + 产物）；
- 开发集真实批次 1–2 轮（需供应商可用与预算；**FL-D118 阻塞**，改用 OpenCode Go 需产品负责人指示）；
- 对照 `round14-05`（220/236、1240 calls、$0.9053）：完成率、确定性占比、调用数、成本；
- 达标后按既有流程冻结；留出 H01–H08 照旧只读一次。

## 6. 指标

| 类别 | 指标 | 目标 |
| --- | --- | --- |
| 主 | 确定性产出占比 | ≥70%，力争 80% |
| 主 | 开发集目标完成率（对照 0.9322） | 不降低 |
| 主 | `kept` / `not_executed` / 假完成 | 不增加 |
| 过程 | 模型调用数/合同（compose + verify） | 相对 round14-05 不增 |
| 过程 | `RECALL_COMPOSE_*` 失败分布 | 下降 |
| 过程 | V2 拦截数 / V3 verdict 分布 | 记录并分类 |
| 安全 | 政策要点偏离（V1/V3 记录） | 结构破坏 = 0；主题错配被拦（FL-D119 为回归样例） |

## 7. 依赖、风险与阻塞

- **已具备的裁定**：FL-D106（compose 两硬约束可推翻 → 由 V1/V2/V3 接管）、FL-D104（G08-1/G08-2 属正常替换、按收费性质实例化）。
- **风险**：
  1. V2 diff 误报（合法改写被判未授权）→ 先旁路观测，灰度上线；
  2. tier 前置条件误判 → **统一降级 tier3**（安全侧），并记录降级原因；
  3. 异模型不可用 → 默认同模型独立调用，`FUNDLEX_VERIFY_MODEL` 可选。
- **阻塞**：真实批次验证受 FL-D118（供应商余额）影响；离线部分不受影响。

## 8. 版本控制与操作纪律

- 每阶段独立 commit；发布走 `tools/deploy/publish_workspace.sh`；**批次运行期间禁止发布**（FL-D096）；
- 每阶段完成后更新 `docs/ACTIVE_HANDOFF.md` 与集中记录 FL-D120 变更记录；
- 若发现新问题：追加集中记录条目，不改写历史结论。

## 9. 待产品负责人裁定项（本计划内）

| # | 待裁项 | 建议 |
| --- | --- | --- |
| 1 | V3 复核不通过时：拒绝该条（进 unresolved/例外）还是标记"存疑/证据待核"照交？ | 建议先"标记存疑照交"（符合"复核只标记不回撤"），观测后再考虑收紧 |
| 2 | V3 是否必须使用**不同模型**？（默认同模型独立调用） | 默认同模型；需要异模型时请指定端点/模型（凭据照旧不入库） |
| 3 | 无服务组产品（A+Y 等）替换文本的最终写法 | 建议"丢弃命名缺失组的固定句、其余照改"（Phase 3 方案） |
| 4 | "按收费性质"口径是否扩展到 G11（FL-D104 第 6/7 项）及 G14/G16 同族 | 建议同口径扩展，随 Phase 2/3 一并确认 |
| 5 | 评分语义是否同步放宽（V1/V2/V3 通过的改写是否视为完成） | 属冻结范围，建议 Phase 5 前单独裁定 |

## 10. 附：术语与引用

- **授权窗口**：一次操作允许改动的文本范围（replace 的 old→new 差异句段、delete 的目标 span、append 的插入点）；窗口外任何字符变化都视为未授权。
- **must_add / must_remove / must_preserve**：由规则 + Facts 推导的"必须新增/必须删除/必须保留"清单（Policy Components）。
- 数据与代码引用：`var/recall-first-evaluation/p6-dev-round14-05/`、`guides/builtin_guide_v1.json`、`fundlex/recall.py`（`plan_target`/`compose_variant`/`_component_ok`）、`fundlex/recall_pipeline.py`（`_finding_evidence`/`_rule_required_text`）、`/home/opencode/B_CLASS_REPORT_FINAL.md`。
- 相关条目：FL-D104、FL-D105、FL-D106、FL-D119、FL-D120（均见 `docs/DETAIL_ISSUES_AND_RESOLUTIONS.md`）。
