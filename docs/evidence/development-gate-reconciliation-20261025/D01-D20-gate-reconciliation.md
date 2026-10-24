# D01–D20 开发集固定分母对账（2026-10-25）

本文件把固定的 D01–D20 分母与保留的真实工作台证据逐份对齐。它不改写历史 report、labels、gold、scorer 或 DOCX。dev-05 批次对应 snapshot-05；target-19 对应 snapshot-18；target-20 对应 snapshot-19。

## 结论

**当前开发集 gate 未通过，20 份中 0 份可计入当前 snapshot-19 gate。** 只有 D06 有 snapshot-19 的真实工作台证据，但其 G06 单向 Y 类转换仍未取得业务授权，Claim Replay 为 false，delivery 为 incomplete。D04 的最近独立整合同通过属于 snapshot-18；其他 18 份合同的主要真实产物来自更早的 dev-05；其中 D02、D16、D17 有历史整合同业务复核通过，D18 历史复核失败，其余 15 份仍 pending。

## 固定分母与门禁

- selection：`/home/opencode/fundlex/var/recall-first-evaluation/p6-current/selection.json`；selection SHA：`95fe8121d5f0aceb4febf9cc76a79fde78cf44f711e9a6f029b08eb6ee5643f3`。
- 分母固定为 D01–D20 共 20 份开发合同，holdout 共 8 份。
- 当前候选为 snapshot-19 / build `e2ac0f14429de4fdd71e631d10c18b27f1366c8337e797b4c834b5adf6611229`。
- 计入 gate 必须同时具备：当前快照真实普通工作台证据、下载产物机械核验、Claim Replay 与 delivery gate 通过、独立整合同业务复核通过。
- 旧快照结果、目标计数、任务 complete、机械文件通过或段落级检查不能单独关闭整合同 gate。

## 汇总

| 指标 | 数量 |
|---|---:|
| D01–D20 固定分母 | 20 |
| 已有 snapshot-19 证据 | 1 |
| 已有 snapshot-19 且 delivery complete | 0 |
| 机械 artifact pass（最新保留证据） | 20 |
| Claim Replay verified（最新保留证据） | 5 |
| 独立整合同业务复核通过 | 4 |
| 独立整合同业务复核 pending | 15 |
| 独立整合同业务复核未完成 | 1 |
| 当前 gate eligible | 0 |

## 逐合同对账

| 合同 | 最新证据 | 快照 | delivery | mechanical | Claim Replay | 独立整合同复核 | 当前 gate |
|---|---|---|---|---|---|---|---|
| D01 | dev-05 | snapshot-05 | incomplete | PASS | FAIL | PENDING | NO |
| D02 | dev-05 | snapshot-05 | complete | PASS | PASS | PASS_FOR_HISTORICAL_INDEPENDENT_BUSINESS_REVIEW | NO |
| D03 | dev-05 | snapshot-05 | incomplete | PASS | FAIL | PENDING | NO |
| D04 | target-19 | snapshot-18 | complete | PASS | PASS | PASS_FOR_D04_INDEPENDENT_BUSINESS_REVIEW | NO |
| D05 | dev-05 | snapshot-05 | incomplete | PASS | FAIL | PENDING | NO |
| D06 | target-20 | snapshot-19 | incomplete | PASS | FAIL | INCOMPLETE_G06_REVIEW_REQUIRED | NO |
| D07 | dev-05 | snapshot-05 | incomplete | PASS | FAIL | PENDING | NO |
| D08 | dev-05 | snapshot-05 | incomplete | PASS | FAIL | PENDING | NO |
| D09 | dev-05 | snapshot-05 | incomplete | PASS | FAIL | PENDING | NO |
| D10 | dev-05 | snapshot-05 | incomplete | PASS | FAIL | PENDING | NO |
| D11 | dev-05 | snapshot-05 | incomplete | PASS | FAIL | PENDING | NO |
| D12 | dev-05 | snapshot-05 | incomplete | PASS | FAIL | PENDING | NO |
| D13 | dev-05 | snapshot-05 | incomplete | PASS | FAIL | PENDING | NO |
| D14 | dev-05 | snapshot-05 | incomplete | PASS | FAIL | PENDING | NO |
| D15 | dev-05 | snapshot-05 | incomplete | PASS | FAIL | PENDING | NO |
| D16 | dev-05 | snapshot-05 | complete | PASS | PASS | PASS_FOR_HISTORICAL_INDEPENDENT_BUSINESS_REVIEW | NO |
| D17 | dev-05 | snapshot-05 | complete | PASS | PASS | PASS_FOR_HISTORICAL_INDEPENDENT_BUSINESS_REVIEW | NO |
| D18 | dev-05 | snapshot-05 | incomplete | PASS | PASS | FAIL_OR_REVIEW_REQUIRED | NO |
| D19 | dev-05 | snapshot-05 | incomplete | PASS | FAIL | PENDING | NO |
| D20 | dev-05 | snapshot-05 | incomplete | PASS | FAIL | PENDING | NO |

D02、D16、D17 的 snapshot-05 独立逐段复核通过，但不能替代 snapshot-19 重跑；D18 的 snapshot-05 复核因 G17 重复/残留文本失败。D04 的 target-19 独立复核为 19/19 段通过，但仍是 snapshot-18；D06 的 corrected 复核为 19/19 段、25/25 断言通过，但结论为 `INCOMPLETE_G06_REVIEW_REQUIRED`，因为整合同业务批准不能替代 G06 未决。

## 预算与复测缺口

- 共享 ledger：1701 requests / `$1.64408310`，reserved=0；按 cap 2000 requests / `$2.00000000`，剩余 299 requests / `$0.35591690`。
- 最小当前快照补测方案：保留已有 snapshot-19 D06，补跑其余 19 份；按 dev-05 逐合同观察值估算 602 requests / `$0.60031875`，比现有余量少 303 requests、`$0.24440185`。
- 干净的 20 份全量重跑基线：628 requests / `$0.63222030`，比现有余量少 329 requests、`$0.27630340`。以上均不含重试、复测和 G06 修复所需模型调用。

## 下一步

- 在获得新增或明确授权的评测预算前，不启动无法完成固定分母的随机真实批次。
- 预算到位后冻结与 snapshot-19 一致的新开发批次，优先补齐 D01–D05、D07–D20 的真实普通工作台证据，并为每份合同完成独立整合同业务复核；D06 需先处理或取得 G06 业务决定。
- 在 20 份开发 gate 通过前，继续阻断 holdout、正式引擎 release 和最终普通工作台 E2E。

机器可读明细见同目录的 [`D01-D20-gate-reconciliation.json`](D01-D20-gate-reconciliation.json)。
