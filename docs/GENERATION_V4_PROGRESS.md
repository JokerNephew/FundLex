# 文本生成策略 v4 —— 实施进度与版本控制（2026-10-19 起）

> 依据：[`GENERATION_STRATEGY_PLAN_2026-10-19.md`](GENERATION_STRATEGY_PLAN_2026-10-19.md)（v4）。
> 状态：**实施中**（2026-10-19 产品负责人批准开始实施）。本文记录每 Phase 的基线、验收、commit 与遗留项。
> 纪律：每 Phase 独立 commit、独立测试；批次运行期间禁止 `publish_workspace.sh`（FL-D096）；新逻辑默认由开关 `FUNDLEX_GENERATION_STRATEGY=legacy` 关停（零行为变化）。

## Phase 0 —— 基线冻结（✅ 2026-10-19）

| 项 | 值 |
| --- | --- |
| 实施起点 commit | `9546a81`（含引擎侧 FL-D118 修复 `46afe2f`/`d6cc8ce`/`03fbbfa` 等） |
| Guide | `guides/builtin_guide_v1.json`，sha256 `5d5eebe989885cba6614…` |
| Scorer（冻结，不改） | `tools/evaluation/p6_score.py`，sha256 `fffe2316e05eb9fe9a5c…` |
| 主基线批次 | **`p6-dev-round14-09`**：dev 221/236 = **0.9364**（kept 11 / not_executed 4；891 calls / $0.7435） |
| 历史对照 | `p6-dev-round14-05`：220/236 = 0.9322（1240 calls / $0.9053，DeepSeek，供应商混杂注明） |
| 在跑批次 | `p6-dev-round14-10` 运行中（结果出来后补记；若有效可作为最新对照） |
| 既有测试基线 | `691 passed / 6 skipped / 1 failed`（既有 references 缺失项） |

## Phase 1 —— Registry + Telemetry + Coverage Ledger 只读视图（✅ commit `53b6d0f`）

- 交付物：`fundlex/generation/`（`flags.py` / `types.py` / `registry.py` / `router.py` / `coverage.py`）、`tools/evaluation/generation_mix.py`、测试 `tests/test_generation_registry.py`（9 项）、`tests/test_generation_coverage.py`（5 项）。
- 开关：`FUNDLEX_GENERATION_STRATEGY=legacy|registry_shadow|registry`，**默认 legacy**（新逻辑不可达 → 零行为变化）。
- 验收：
  - 全量 `pytest tests -q` → **704 passed / 6 skipped / 1 failed**（唯一失败为既有 references 缺失项；本 Phase 新增 13 项全过）；
  - `generation_mix` 在 `p6-dev-round14-05` 精确复现基线：**284 条编辑 / 确定性 183（64.4%）/ 模型 71（25.0%）/ merged 30（机械合并）**；
  - Registry 覆盖全部 22 条规则（测试对 guide 强制比对）；未登记规则回退 Tier3 安全侧；事实未核验 → 阻断（不降级 Tier3）。

## Phase 2 —— V1/V2 影子验证 + FL-D119 根因修复 + G11 定位回归（✅ commit `a6d7e60`）

- 交付物：
  - `fundlex/generation/validators.py`：V1（保护字面量/数字溯源/必需项覆盖）、V2-A（边界门）、V2-B（变更解释门，三级处置 EXPLAINED / UNEXPLAINED_SOFT→V3 / UNEXPLAINED_HARD→FAIL）；
  - `fundlex/recall.py` 根因修复：① `find_old_text_all` 模糊分支加"主题翻转/数字翻转"守卫（申购↔赎回等一字之差不再是命中；FL-D119）；② `satisfied_by_new_text` 尾句通道要求规则主题词（"并在招募说明书中列示。"类通用尾句不再误判已满足）；
  - `tools/evaluation/validator_shadow.py`：对既有批次产物离线回放（零模型调用；每段落一次校验、授权取该段全部编辑的并集）；
  - 测试新增 **18 项**（validators 11 + FL-D119 常驻回归 7，含 `D01/p227` fixture）。
- 验收：
  - 全量 `pytest tests -q` → **722 passed / 6 skipped / 1 failed**（既有 references 缺失项；Phase 2 新增 18 项全过）；
  - **FL-D119 常驻回归**：`D01/p227` 在影子回放中被抓（`UNEXPLAINED_HARD: protected:赎回`）；真阳性同时覆盖 G05 p135（真实误改：覆盖"调整前基金管理人需及时"＋句号断句，与引擎自身 audit 的 `wrong` 一致）；
  - **影子统计（round14-09，有效批次 13 例）**：155 个段落校验 → **FAIL 1（0.6%）**、soft-flagged 54（≈35%，后续 Phase 的 V3 路由样本）；唯一 FAIL（D04 G12 p198，`protected:25%`）为**待人工复核**项——离线授权推导未命中合同变体，初步判为工具侧误报；
  - 已知限制：位置对齐为按段落序号（产物删段后可能错位）；每段授权并集可能高估宽松度；均在工具 docstring 注明。
- 下一步：Phase 3（Facts 扩展 + 三态证据），随后 Phase 4 Tier1（G14/G09/G15/G17）。

## Phase 3–8 实施记录（代码已落地；外部复查遗留见下）

| Phase | 内容 | commit |
| --- | --- | --- |
| 3 | Facts schema v2 三态（`share_class_structure` + 渠道组 + `fact_status`；facts prompt v2） | `f492701` |
| 4 | Tier1：G14 结构化集合删除（句尾收敛/保序重建两模式）、G15/G17 删除前置路由、G09 短语 splice；开关 `FUNDLEX_GENERATION_STRATEGY=registry` | `24e39d6` `9b0fdb0` |
| 5 | Tier2：G08/G11 干净整句的确定性政策替换 | `287be26` |
| 6 | Tier3：compose 三层验证（V1/V2 程序门 + V3 独立模型复核 `recall_verify_v1`；失败重试 1 次后 unresolved） | `1ecd93c` |
| 7 | **G16 Pilot：未按试点实现**——G16 是 append，planner 在 append 分支直达 `guide_text`，compose 永不触发；Registry 写 COMPOSE 与执行不一致。**待产品裁定 A（确定性 append + 智能 satisfied，推荐）/ B（组件融合）** | — |
| 8 | Artifact Claim Replay：对**已写入 DOCX** 重放替换缺失/未变化/数字/未授权检查，失败进 unresolved（阻塞 complete） | `1ecd93c` |

## 外部复查（2026-10-19，另一 agent）响应

> **第二份复查（源材料版，同日）**：另一 agent 在阅读**指引原文（68–88 段）+ 合同原文**后提出 **6 项 P0 + 6 项 P1**，核心结论：风险重心应从"生成策略"前移到"Facts/Applicability 层"（"程序越确定，错得越稳定"）。已核对其关键代码断言全部属实（append 首句 satisfied=`required.split("。")[0]`、`condition_matches` 裸 bool、`class_label('人民币份额')='人民币类基金份额'` 叠字、`DEFAULT_EXCLUDED_TYPES=etf,money_market,interbank_cd`、`service_group` 定义不严格、G16 registry 的 `preserve existing_payment_*` 与指引冲突）。**处置队列（P0-A~D + P1 列表）见下方"待实施队列"；用户指示暂缓动手。**
>
> **ETF/同业存单范围裁定（2026-10-19 用户确认）**：**维持全局排除**（`DEFAULT_EXCLUDED_TYPES` 现状），依据 C-R 设计文档 §9 的默认 + 本次用户确认；后续按"policy override + 依据"记录，不再作为未审视默认。（货币基金排除已有既有裁定。）
>
> **REITs/封闭式商业不动产补充裁定（2026-10-20 用户确认）**：REITs（基础设施、封闭式商业不动产）同样不用修改，纳入整份排除；默认集合扩为 `etf,money_market,interbank_cd,reits`。**ETF 联接基金不属于 ETF，正常修改**（`_is_etf_feeder` + `recall_facts_v3`，FL-D132）。代码、测试与真实模型核验已完成（**未发布**），详见 FL-D130/FL-D132。

### 已核对的代码断言（证据行号，2026-10-19）

| 断言 | 位置 |
| --- | --- |
| append 已满足仅看首句 | `fundlex/recall.py:1765` |
| `condition_matches` 裸 bool，UNKNOWN 被吞成 False | `fundlex/recall.py:2372` |
| `class_label` 对非标准类别名生成叠字 | 实测：`人民币类、美元现汇类基金份额` / `A类人民币类基金份额` |
| 全局排除默认值 | `fundlex/recall_pipeline.py:52` |
| `service_group` 不要求 `subscription_fee==False` | `fundlex/recall.py`（service_group property） |
| G16 registry `preserve existing_payment_*` 与指引冲突 | `fundlex/generation/registry.py`（待改） |

### 待实施队列（P0，用户批准后按序开工）

- **P0-A** Condition 三值（TRUE/FALSE/UNKNOWN）+ UNKNOWN 不得进修改分支 + **Router 接成 planner 唯一入口**（两层同修）；
- **P0-B** 类别事实模型（`source_display_name`、币种维度分离、`class_label` 保原文、严格 fee group、VERIFIED_EMPTY）；
- **P0-C** G15+G16+G17 业务闭环 + G16 组件级 coverage + **B 融合（修正后：不保留旧支付机制，融合仅整合 4 个新组件）**；
- **P0-D** G08/G11 缺服务组改为"按组件丢弃"而非丢整条 operation。

### P1 队列

append semantic site anchor、`(operation_id, site)` 覆盖粒度、G06/G13/G17 确定性签名、G14 集合双差、claim replay 按 operation 重放、CI（非优先）等。

| 项 | 状态 |
| --- | --- |
| **P0-1** Router 未接入 planner（UNKNOWN FACT 阻断未从架构保证） | **已实施**（三态 + Router gate/route 记录，registry） |
| **P0-2** V3 按 default_tier 而非 actual tier 触发 | **已修**（进入 compose 即 actual tier3 → V3 必跑；新增 G08/G14 fallback-compose 测试） |
| **P0-3** G16 Tier3 pilot 未实现 | **待产品裁定 A/B**（推荐 A） |
| **P0-4** Coverage Ledger 未接 gate + `operation_id` 回退 | **已实施**（operation_keys + gate 读投影、失配 fail-closed） |
| **P1-1** Tier 标签/遥测 | 部分已修（docstring 勘误：干净整句=Template 级符合计划 §19.1；显式 tier 字段随 P0-1） |
| **P1-2** VERIFIED_EMPTY 闭环 | 部分：空组仍 UNKNOWN（保守）；G16 已按组件判定 |
| CI（GitHub Actions） | 建议项，非优先 |

**本地真实链路验证（registry 开关，真实模型）**：

- D01：G14 p231 收敛为指引原文、G09 p227 splice、G15 p1221 前置删除，audit 均 `completed`；**claim replay: checked=17 / failures=0（verified）**。
- D16：G14 p224 正确附加"销售服务费率"、G09 p219 双修正（audit 由 incomplete→completed）；`composed` 归零。
- 测试：全量 **750 passed / 6 skipped / 1 failed**（唯一失败为既有 references 缺失项）。

## 批次预登记（Phase 4–8 验收）

> **状态（2026-10-19）**：**用户指示停止**——`p6-dev-round14-11` runner 与守候脚本均已终止；D01 在飞任务于 15:20:17 后停止，已确认无任何运行活动（`checkpoints/`、`model_budget.sqlite` 无写入、无 `p6_run` 进程）——**批次作废、不得评分**（对照 round14-06/14-07 惯例）。D01 无 result.json，产物不予采信。

| 项 | 值 |
| --- | --- |
| 批次 | `p6-dev-round14-12`（dev 20 例；14-11 已停止作废，本批为 P0 修复后的重跑） |
| 开关 | `FUNDLEX_GENERATION_STRATEGY=registry`（env 备份 `.bak-genv4`；**当前仍启用，未回滚**——如需回到验证过的行为：还原该备份并重启服务） |
| 目的 | Phase 4–8 验收：确定性占比、compose 下降、claim replay 结果、完成率不降（对照 14-09 221/236） |
| 预算 | ≤1100 calls / ≤$1.0（flash 目录价） |
| 回滚 | 批内异常 → 还原 env 备份并重启；不达标 → 记录并保留 `legacy` 默认 |

## Commit 记录（本计划）

| commit | 内容 | 测试 |
| --- | --- | --- |
| `53b6d0f` | Phase 1：registry + router + coverage view + mix tool（flag 默认 legacy） | 新增 13 项通过；全量 704/6/1（既有失败） |
| `2e37253` | Phase 0/1 文档：基线冻结 + 计划状态改"已批准/实施中" | — |
| `a6d7e60` | Phase 2：V1/V2A/V2B 影子验证器 + FL-D119 根因修复 + G11 回归 + 离线回放工具 | 新增 18 项通过；全量 722/6/1（既有失败） |

## 遗留与阻塞

- 真实批次验证受供应商与预算约束；批次运行期间不发布（FL-D096）。
- FL-D119 修复后需在下一有效批次观察 `D01/p227` 不再产生误配（fixture）。
- 评分口径（scorer 升级）仍按"先冻结 → 实测 → 单独裁定"执行（计划 §39）。

## Recovery 架构改造（2026-10-20，本地已验证/未发布）

- 分支 `refactor/recovery-architecture`，详细设计见 [`RECOVERY_ARCHITECTURE.md`](RECOVERY_ARCHITECTURE.md)，问题记录见 FL-D133。
- 新增：`fundlex/models/`（Primary/Review 独立角色）、`obligations.py`（ALL_OF/ONE_OF/BRANCH + Ledger）、`applicability.py`、`facts_recovery.py`、`targeting.py`、`recovery/`、`delivery.py`、`generation/components.py`、`generation/joint.py`。
- 硬门：`validate_edit` 成为确定性/Compose/Joint 的统一入口；claim replay 增加文档级与段内边界证明；G16 组件×站点；费用主题与列表序号修复。
- 验证：全量 **864 passed / 6 skipped**；round14-12 离线 shadow **222 段 / 0 hard FAIL**；真实 D01 早期一版报 complete，但 Business Reviewer 发现 G17 残句/G15 正文摘要不一致，属 false_complete；新增残留与副本硬门后 D01 被如实阻塞为 partial。D02/D03/D11 的失败也被标 partial（D11 旧版为 false_complete）。
- 未完成：20 例 dev 对照、514 全量、生产发布与工作台端到端；G09/G01/G15 业务残留、audit context 分批、无目标规则 T3 默认关闭；尚未取得最新硬门下真实 complete 样例。
