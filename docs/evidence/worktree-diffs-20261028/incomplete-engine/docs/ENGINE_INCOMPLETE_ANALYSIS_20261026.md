# Engine incomplete 离线分析与修复交接（2026-10-26）

- 工作树：`/home/opencode/.local/share/opencode/worktree/29a9a9/incomplete-engine`，detached HEAD，基线 `1131a8c`。
- 范围：定位、复合目标、生成与重叠；未调用真实模型，新增模型费用为 0，未部署，未修改集中问题记录。主 agent 负责登记集中问题并执行后续真实验收。
- 项目文档已阅读；既有 FL-D052、FL-D118、FL-D157–159、FL-D275 修复作为当前基线，不将历史故障重新宣称为新发现。

## 确认的新根因：链式重叠按二元冲突依次消费编辑

建议主 agent 登记 **FL-D300**（仅为本工作树查重后的建议，合并时仍须在主工作区查重）：`Joint Compose 未按重叠连通分量规划，链式冲突可导致全部编辑退出最终计划`。

- 复现：同一段三个编辑 A=[0,3)、B=[2,5)、C=[4,7)。`merge_edits()` 返回 A↔B、B↔C 两项 `RECALL_EDIT_OVERLAP`。
- 根因：`_resolve_overlaps_with_joint_compose()` 对每个冲突分别规划；A+B 成功后 B 已 consumed，B↔C 留作未解决。`plan_edits()` 随后重新合并，A+B 与 C 仍重叠，最终全部相关 target 被过滤并标记 unresolved。纯删除也会发生，无需任何模型调用。更长链及冲突输入顺序变化同源。
- 修复：先根据同段实际 edit 身份构造冲突连通分量，再将整个分量交给现有 `joint_delete` 或 Joint Compose。跨段 composite 的同 target 其他编辑不参与此段分量。保留原有 operation 归因、Validator/Review 和失败关闭路径，无合同名特判。
- 失败关闭：联合生成返回 None 时，仍保留全部原编辑与包含全部 target 的冲突；不产生已验证的联合替换。
- 文件：`fundlex/recall.py`、`tests/test_final_validation_regressions.py`。首个修复提交 `66f6330`；后续提交补充边界测试、简化分组合并并包含本交接。
- 验证范围：确定性 DOCX 夹具与替身 Joint Compose；尚无证据证明生产 D01/D02/D04 的具体错误实例由该缺陷触发。

## 五类错误的当前判断

| 错误 | 路径与结论 |
| --- | --- |
| `RECALL_EDIT_OVERLAP` | `merge_edits` → `_resolve_overlaps_with_joint_compose` → 最终 merge/ledger；确认并修复上述链式消费缺陷。 |
| `SURVEY_QUOTE_UNRESOLVED` | `_survey_targets_from_hits` 单段 `resolve_quote` 失败时登记 coverage gap；未发现可确认的新通用缺陷，不放宽引文绑定。 |
| `RECALL_TARGET_UNRESOLVED` | `_plan_target_inner` 拒绝未绑定目标；`_rebind_unresolved_targets` 已具跨段 quote/reference 重绑定。既有修复回归通过。 |
| `RECALL_COMPOSE_FIXED_TEXT_MISSING` | `compose_variant` 要求输出包含固定政策文本；这是现有硬校验。已读生成与组件校验路径，未确认新的低范围根因，不放宽固定文本门禁。 |
| `RECALL_TARGET_COMPOSITE_UNRESOLVED` | `plan_composite_target` 校验 parts 与 compact 坐标；既有空白映射、逐片段校验和复合删除回归通过，未确认新的低范围缺陷。 |

## 验证记录

共享解释器为 `/home/opencode/fundlex/.venv/bin/python`；本工作树没有独立 `.venv`。

```bash
PYTHONPATH=. /home/opencode/fundlex/.venv/bin/pytest -q tests/test_final_validation_regressions.py -k 'overlapping_composite_deletes or transitive_overlap'
# 5 passed, 105 deselected

PYTHONPATH=. /home/opencode/fundlex/.venv/bin/pytest -q tests/test_recall_core.py tests/test_recall_pipeline.py tests/test_operation_execution_closure.py tests/test_composite_slice_delivery.py tests/test_split_definition_append.py tests/test_merged_definition_append.py tests/test_final_validation_regressions.py --maxfail=1
# 修复前既有套件 256 passed / 70.74s；最终 260 passed / 76.85s

PYTHONPATH=. /home/opencode/fundlex/.venv/bin/python -m py_compile fundlex/recall.py tests/test_final_validation_regressions.py
git diff --check
# 均通过
```

另在独立 Python 进程中从 `git show 1131a8c:fundlex/recall.py` 解析 AST，只替换内存中的旧 `_resolve_overlaps_with_joint_compose`，运行 `-k transitive_overlap --tb=short`：**4 failed / 106 deselected**。两项纯删除仍残留冲突；生成成功/失败夹具分别触发 2/3 次 Joint Compose，违反整连通分量一次决策。未覆盖磁盘源码，随后当前实现再次 5 项通过。

## 未完成与下一步

- 建议登记 FL-D300 后合入两个代码提交；不要覆盖主工作区并行更改。
- 真实故障报告须按 target、operation、parts、source geometry 和原始错误上下文逐项对齐；不能仅凭相同错误码将所有 incomplete 归因于本修复。
- 未运行整个仓库全量回归、真实模型或用户端到端交付；本任务明确禁止真实调用。生产修复是否改善 D01/D02/D04 仍待主流程在预算登记与正式入口下验证。
- 本工作树未启动后台进程或子 agent；无需恢复模型运行。

## 2026-10-26 固定计划工作版的独立复核边界

- 固定 checkpoint replay 已形成 D01/D04 各 19 条计划，但完整流程仍停止：D01 在 `recall_inventory` sweep repair 的新上下文 `9a513a03fc8cbc455246cf14d74b76ac6faa18ef30e11efecddc5b5dc1aa7773` 停止，D04 在 `recall_audit` 新上下文 `bedbe9797d768a8ffea4253b7418ab2074c6719aee24a11c820cb3c18148382` 停止。两者报告均 `delivery_status=not_generated`、`PROCESSING_FAILED`；不能视为正式交付，也不能据计划数关闭未完成。
- 已从固定计划离线生成工作版 DOCX，并用 `/tmp/opencode/incomplete-remediation-20261026/verify_fixed_plan_artifacts.py` 重新读取真实原件/工作版：D01 final SHA `4280444cb3481806a1a3ee6e131c29c73dc28463ceeb1533f6d163acda7386bc`、redline SHA `f2f8701b58be54f4aed5282e0140e9147b1a1d14cb9ff32157ad2905f422a724`；D04 final SHA `4410d210e895cc2a669677c08f6aef0b9c741290fb3851a3ee94d6da38c4d6b4`、redline SHA `b21880624b1f4e5241c6556b04a615643a23766cf70e199299230ee17d4f9044`。两份均机械通过：计划与 DOCX 文本一致、接受修订等于 final、拒绝修订等于 source、无 final 修订残留，19/19 Claim Replay 通过；这些是离线工作版证据，不是用户交付。
- 离线工作版首次 Claim Replay 的两个 G22 `CLAIM_OPERATION_APPLICABILITY_UNPROVEN` 是夹具调用错误，不是引擎 applicability 缺陷：复核脚本把报告中已扁平化的 `facts` ledger 当作嵌套 FACTS_SCHEMA 传给 `facts_from_value()`，丢失 `floating_management_fee.quote`，因而 G22 的 `is_floating_fee` 前置证据变为 UNKNOWN。用扁平 ledger 重建嵌套回答并逐字回查真实 DOCX 后，D01/D04 G22 均为 `TRUE`、Claim Replay 均为 true；负向检查删除浮动费引文仍为 UNKNOWN，说明门禁未被放宽。原脚本及更正复核脚本均在 `/tmp`，未写入正式代码。
- D01 工作版 p228 的真实残留仍存在：`本基金 C 类基金份额不收取申购费。` 在 G11 新替换文本后保留一次；独立 sweep 结果为 `pending / RESIDUAL_CONFIRMED`，必须继续阻塞。D04 G03 仅绑定 p83；旧 p89 target 保留为 `TARGET_SOURCE_MISMATCH`、`out_of_scope=true`，p89 实际只执行 G05。
- 本轮新增定向回归为 `156 passed` 与 `97 passed`；`py_compile`、`git diff --check` 通过。工作树未提交、未部署、未调用真实模型；新增模型费用为 0。主工作区须将新发现/状态变化登记到集中问题文档，并在完整 checkpoint、G11 残留处理及真实用户链路完成前保持 incomplete/NO-GO。
