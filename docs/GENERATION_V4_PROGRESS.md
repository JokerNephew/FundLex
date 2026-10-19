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

## Phase 2 —— V1/V2 影子验证 + FL-D119 根因修复 + G11 定位回归（进行中）

- 见下方 commit 记录。

## Commit 记录（本计划）

| commit | 内容 | 测试 |
| --- | --- | --- |
| `53b6d0f` | Phase 1：registry + router + coverage view + mix tool（flag 默认 legacy） | 新增 13 项通过；全量 704/6/1（既有失败） |

## 遗留与阻塞

- 真实批次验证受供应商与预算约束；批次运行期间不发布（FL-D096）。
- FL-D119 修复后需在下一有效批次观察 `D01/p227` 不再产生误配（fixture）。
- 评分口径（scorer 升级）仍按"先冻结 → 实测 → 单独裁定"执行（计划 §39）。
