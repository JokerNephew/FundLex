# 2026-10-18 引擎修正计划（FL-D112–FL-D115 + FL-D110 待决项）

## 目标

在不改变“模型负责语义、代码负责结构/证据/执行”的前提下，修掉已确认的实现缺陷；
每项都有离线测试；发布后用真实开发集批次对照 round14-03 基线。

## 阶段与顺序

1. **FL-D112 内容校验接线 + composite 坐标**
   - `validate_edit_plan`：`content_check(edit) is False` → 抛 `DocxError("CONTENT_CHECK_FAILED")`。
   - `_composite_part_slice`：改用 `compact_offsets`，与 `plan_composite_target` 同坐标系。
   - 测试：篡改 composite 必须被拒；带空白锚点的 composite 必须通过。
2. **FL-D110 三项**
   - target 身份：`rule_id + location + span hash`（不再用 quote 前 60 字）。
   - 复合删除证据：逐 part 校验原切片已消失，而不是只看第一个 location 是否为空。
   - `_plan_by_target`：无 ledger 的 component → `unresolved`（`LEDGER_MISSING`），不再默认 `planned`。
3. **FL-D113 盲窗**
   - sweep ledger 记录 `blind_windows`（无行为变化）。
   - 空范围窗口回退到 `mandatory` 规则（有已知未完成义务才回退，控制噪声）。
4. **FL-D114 引文核验**
   - `_verify_quote` 支持省略号分段校验与跨段拼接，降低假阴性。
   - 不改变 `fund_type` 排除策略（该策略需要重新取证/仲裁，另行评估）。
5. **FL-D115 finding 关闭证据**
   - 先只记录 `resolution_evidence`（delete/replace/append 三类确定性信号），不改变 resolved 判定；
     等真实批次评估后再决定是否把“静默 resolved”收紧。

## 版本控制与进度

- 每阶段一个 commit；阶段完成后跑相关测试 + 全量 `pytest tests -q`。
- round14-03 在跑期间**不发布**；完成后先记录基线（batch.json/score），再发布全部修正。
- 发布后跑 `p6-dev-round14-04`，与 14-03、round11 对照；供应商切换与多项修正合并，需在报告中注明混杂。
- 失败即回滚到上一个 commit + 上一份部署；不带着失败测试发布。
- 文档：每阶段更新 `docs/ACTIVE_HANDOFF.md`；新发现的细节问题追加到集中记录。

## 预算

- round14-04：20 例，≤1000 calls，≈$0.5–0.8；账本当前 17462 requests / $14.4908。
- 发布与批次期间禁止并发发布；批次前清空/归档 trace。
