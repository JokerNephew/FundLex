# EVAL 评测线全覆盖审计签认（2026-11-01）

> 依据 docs/COVERAGE_MATRIX_20261101.md（主线 commit 3cab25b）名下两行：语料 500+ 剖析 + tools/evaluation/ 全部 58 个 .py。
> 纪律遵守：只读代码、只写本树审计文档；逐文件签认，无抽样。
> 方法：58 文件按行数螺旋分 4 组派只读审计员逐行审读 + 候选缺陷主审计逐一复验后入册；主线关键量具（p6_score=现行 p6-score-4-appendwindow-20261101）由本复核定，其 before=6/after=6 对称窗口为 FL-D790 已审定形态，不作发现。

## 行 1：语料 500+ 剖析 → ✅ 已完成

- 产物：`docs/engine/CORPUS_TYPOLOGY_20261101.md`（确定性解析 578 物理份 → 542 唯一；类型学/结构/费用形态/失败家族相关性矩阵/机制方向 7 条/数据治理 3 项）。
- 附带发现已入册：FL-D865 补证（BH06 protection enforcement=0）；语料 18 名 ×3 副本去重口径（写于 CORPUS_TYPOLOGY §5）。
- 签认：✅ 完成，无新增未登记发现。

## 行 2：tools/evaluation/ 58 文件逐文件签认

审计完成：58/58 逐文件签认如下。

## 逐文件签认总表（58/58，候选→主审计复验→入册）

| 文件 | 签认 |
| --- | --- |
| tools/evaluation/action_fixture_audit.py | ✅ FL-D869族外【FL-D984】 |
| tools/evaluation/budget_preflight.py | ✅ 无发现 |
| tools/evaluation/build_labels_v2_20261028.py | ✅【FL-D984】 |
| tools/evaluation/build_revision_review_packet.py | ✅【FL-D985】 |
| tools/evaluation/compare_benchmark.py | ✅【FL-D984】 |
| tools/evaluation/compare_e2e.py | ✅【FL-D985】 |
| tools/evaluation/compare_evaluate.py | ✅ 无发现 |
| tools/evaluation/compare_fixture_builder.py | ✅ 无发现 |
| tools/evaluation/compare_gold.py | ✅【FL-D984】 |
| tools/evaluation/compare_wave_runs_20261031.py | ✅ 无发现 |
| tools/evaluation/controlled_regression.py | ✅【FL-D984】 |
| tools/evaluation/corpus_audit.py | ✅【FL-D985】 |
| tools/evaluation/delivery_e2e.py | ✅【FL-D984】 |
| tools/evaluation/development_gate_reconciliation.py | ✅【FL-D985】 |
| tools/evaluation/finalize_first_batch_labels_20261028.py | ✅【FL-D984】 |
| tools/evaluation/finalize_second_batch_labels_20261031.py | ✅【FL-D984】 |
| tools/evaluation/first_batch_label_20261028.py | ✅【FL-D984】（三处，波及在制第二波标签线） |
| tools/evaluation/generation_mix.py | ✅ 无发现 |
| tools/evaluation/matching_audit.py | ✅【FL-D984】 |
| tools/evaluation/p6_label.py | ✅【FL-D984+FL-D985】 |
| tools/evaluation/p6_langfuse_sync.py | ✅【FL-D984】 |
| tools/evaluation/p6_package.py | ✅ 无发现 |
| tools/evaluation/p6_run.py | ✅【FL-D985】 |
| tools/evaluation/p6_score.py | ✅ FL-D867 |
| tools/evaluation/p6_select.py | ✅【FL-D984】(L74 split脆性并入) |
| tools/evaluation/p6_trace_report.py | ✅【FL-D984】(死常量记录) |
| tools/evaluation/pilot_compare.py | ✅ FL-D869 |
| tools/evaluation/prepare_second_batch_run_20261031.py | ✅【FL-D985】 |
| tools/evaluation/production_first_batch_e2e_20261028.py | ✅ FL-D868 |
| tools/evaluation/production_v1_e2e_20261026.py | ✅【FL-D984】(SPA竞态断言+陈旧任务同名) |
| tools/evaluation/real_contract_e2e_20261023.py | ✅ FL-D868 |
| tools/evaluation/real_resume.py | ✅ FL-D868 |
| tools/evaluation/real_scenarios.py | ✅ 无发现 |
| tools/evaluation/recall_run.py | ✅【FL-D985】（gateway 泄漏=第二波前必办） |
| tools/evaluation/release_evidence.py | ✅ FL-D868 |
| tools/evaluation/remediation_probe_20261028.py | ✅ FL-D868 |
| tools/evaluation/replay_checkpoints.py | ✅ FL-D869 |
| tools/evaluation/sample_corpus.py | ✅ 无发现 |
| tools/evaluation/sample_corpus_audit.py | ✅ FL-D868 |
| tools/evaluation/score_first_batch_20261029.py | ✅ FL-D868 |
| tools/evaluation/select_second_batch_20261031.py | ✅【FL-D985】 |
| tools/evaluation/select_unseen.py | ✅ 无发现 |
| tools/evaluation/strategy_consistency.py | ✅ 无发现 |
| tools/evaluation/strictness_audit_20261028.py | ✅【FL-D983】 |
| tools/evaluation/sweep_scope_probe.py | ✅ 无发现 |
| tools/evaluation/task_revision_run.py | ✅【FL-D983】 |
| tools/evaluation/task_workbench_acceptance.py | ✅ 无发现 |
| tools/evaluation/v2_compare.py | ✅【FL-D984】 |
| tools/evaluation/v2_fixtures.py | ✅【FL-D985】 |
| tools/evaluation/v2_handover.py | ✅【FL-D985】(陈旧指向) |
| tools/evaluation/v2_pilot.py | ✅【FL-D983+FL-D985】 |
| tools/evaluation/v2_result_package.py | ✅ 无发现 |
| tools/evaluation/validator_shadow.py | ✅【FL-D985】 |
| tools/evaluation/verify_downloaded_artifacts.py | ✅【FL-D985】 |
| tools/evaluation/verify_first_batch_labels_20261028.py | ✅ 无发现 |
| tools/evaluation/verify_labels_v2_20261028.py | ✅【FL-D984（校验弱化并入）】 |
| tools/evaluation/verify_second_batch_labels_20261031.py | ✅ 无发现 |
| tools/evaluation/word_fixture.py | ✅【FL-D985】 |

**编号口径**：FL-D867/868/869（本池）；**主线已赐号（2026-11-01）**：死运行器族=FL-D983、证据致谎/统计族=FL-D984（含组D校验弱化并入项）、资源/环境族=FL-D985；`production_v1_e2e.py` SPA 竞态断言与 `p6_select.py` L74、`p6_trace_report.py` 死常量、`finalize_second` L550 等低危项并入对应族块记录。
