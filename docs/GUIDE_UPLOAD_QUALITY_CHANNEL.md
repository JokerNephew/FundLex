# 指引上传质量通道（解析→认证→准入）

> 2026-10-31 qa-guide-parse 线（FL-D648 收口 / FL-D660~663）。目标：用户上传的任意指引，
> 能解析成**可执行**的规则才算合格；不合格的每一层都有结构化与人读的原因。
> 「解析得好」的内容标准（人话规则/表达质量/诊断红线/多形态矩阵）见
> 《[新指引解析质量门](GUIDE_PARSE_QUALITY_GATE.md)》(FL-D898，2026-11-01)，两文互补。

## 链路

```
上传 DOCX (POST /api/guides)
  → 排队解析（guide_jobs，owner 串行，3 次尝试上限）
  → worker: extract → parse → 确定性校验 → 独立核验（有界修复 ×2）
  → finish_guide_job 质量门：
      不干净(校验错误/覆盖缺口/核验 finding) → 终态 failed + GUIDE_VALIDATION_UNCLEAN
      干净 → 可执行性金丝雀 executability_report：
        fatal → status=parsed, qualification=needs_review（进复核列表，不可启用）
        pass  → qualification=certified（可启用）
  → set_current_guide 启用闸：qualification + 运行时同谓词 blocking_gaps
  → worker footprint 冒烟：对父版/内置同源基线标 needs_review（advisory，分 source）
```

## 可执行性金丝雀（fundlex/guide_canary.py）

零模型、零合同、确定性，与运行时路由**同谓词**：

- authoritative 操作键必须在 OPERATION_REGISTRY（运行时 `RECALL_OPERATION_REGISTRY_MISSING`
  的精确复演）；部分标识 → PARTIAL fatal；legacy（无标识）文档只走兼容路径、不 fatal。
- 每个分支条件在引擎事实空间 8 组枚举（class_count × 销售服务费 × 浮动管理费）下至少可满足一次。
- 全事实已验证时路由不得阻断；义务编译条目数与操作数一致。

fatal → `GUIDE_CANARY_*` 码 + review 维度（含 12 键清单）+ 启用拒绝。

## 人读诊断（fundlex/guide_report.py）

- `issues.parse_report`：按**主题块**（域标题/编号标题切分，细分标签不切块）给出每块状态
  parsed / split / merged / uncovered / error（canary fatal 会定位到块）/ unparsed，
  附中文原因 `reason_zh` 与修正建议 `remedy_zh`；`summary_zh` 一行总览。
- `CODE_EXPLANATIONS` 覆盖质量门、canary、模型失败类（`GUIDE_MODEL_FAILED:*`）等全部出口码。

## 前端取数

- `GET /api/guides/upload-spec`：上传入口规格说明（支持形态、粒度建议、常见失败模式），
  服务端持文案，前端原样渲染。
- `GET /api/guides/{id}` → `issues_detail.canary` / `issues_detail.parse_report` / `review`。

## 回归与基准

- pytest（零模型）：`tests/test_guide_canary.py`、`tests/test_guide_parse_quality.py`；
  冻结真实事故产物 `tests/fixtures/guides/merged_g15_real_20261031.json`（15 规则合并版，
  12 阻断键断言）与 `fee_rule_v2_issues_20261031.json`（V2 结构化拒绝）。
- 真实模型基准（手动/夜间，不走 CI 门，FL-D445 仅记账）：
  `.venv/bin/python -m tools.guide_parse_benchmark --guides v4 v2 \
   --ledger /tmp/opencode/guide-parse-benchmark.sqlite --engine-smoke N`
  - 通道不变量：v4 → 认证可执行 或 结构化拦下；V2 → 必被结构化拦下；门漏放=基准失败。
  - `--engine-smoke N` 用 references/fee-rule-v2 黄金原件（.docx）走真实任务路径对比
    builtin / 当次新解析版本。
- 2026-10-31 实跑：v4 与 V2 重解析均再现 15 规则合并形态（同一 12 阻断键指纹
  G03:1..G15:1），认证门与金丝雀双双确定性拦下——质量门在真实复发上成立。

## 边界

- 金丝雀判定「新规政策」时（全部键未注册），提示属注册扩展事项而非解析错误（remedy 明示）。
- 结构粒度（块-规则对齐等）只做诊断指标，不做 pass/fail（FL-D661：内置指引自身即违反
  一切简单结构规则）。
