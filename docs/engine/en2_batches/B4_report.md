# 批次B4报告（registry/router/pipeline/v2_pipeline/stage_replay/semantic_contract）

来源：子审计员 ses_e69bd3d3（后台批次，2026-11-01 回报）。原文收录，未改结论。

## 批次B4报告

### fundlex/generation/registry.py
- 结论：✅ 无发现（1 条观察不计发现）
- ① 纯声明式注册表，无状态机；`_UNKNOWN_SPEC` 安全侧默认 + routed 调用者显式查 coverage 的 fail-closed 契约自洽。② fail-closed 路径清晰，无吞错。③ 无用户可见输出。④ G21 "noop 操作占位；按需后续裁定"（line 85-86）为登记在案的占位，非隐秘半成品。⑤ `_build_operation_registry` counts 键与 STRATEGY_REGISTRY 完全一致（G01–G22）；`strategy_for`/`operation_for` 与 recall.py 使用一致。
- 已知命中：FL-D179、FL-D180、FL-D181（均已修复；本文件即修复主体）

### fundlex/generation/router.py
- 结论：⚠️ 候选发现 1 条
- ① 无状态，分层升级/降级规则自洽（clean 升级、mixed 降 T2、unsafe 直降 T3）。② classify_failure 显式表优先于前缀，未知落 UNKNOWN，无吞错。③ EscalationDecision.reason 为内部路由契约，注释明确不面向用户。④ 无 TODO/死代码。⑤ `_strategy_sequence`、`strategy_for_failure` 与 recovery/orchestrator.py:80 调用签名一致；`route_operation` 与 recall.py:7002/7275、guide_canary.py:168 一致。
- 候选发现1：executor 重算无视 spec.executor｜证据 router.py:331-336 `executor = {T.DELETE: "delete", ...}[tier]`，Registry 为 G05:1 等操作显式设定的 `OperationSpec.executor` 字段在路由层被按 tier 重查表覆盖｜当前无实际分歧（override 均与 tier 推导一致），但未来注册自定义 executor 会被静默改写｜建议直接读 spec.executor 或断言一致（机制面，报主线判定）
- 已知命中：FL-D830（深层清理待办，低优先）

### fundlex/pipeline.py
- 结论：⚠️ 候选发现 2 条
- ① 单合同评测路径状态自洽；确认仅被 tools/evaluation/* 调用（生产 worker 走 recall_pipeline）。② except 分支完整回滚 applied→failed，无伪造成功；但 finally 写 report 异常可掩盖成功结果。③ report.md 面向读报告者，含内部字段。④ 无 TODO。⑤ `validate_edit_plan(input_path, edits, ruleset.templates)` 与 docx.py:865 签名一致；`model.calls/.metrics()/close` 与 ModelGateway 一致。
- 候选发现1：finally 块写报告失败会掩盖真实结果｜证据 pipeline.py:216-222 `finally: ... _write_report_markdown(output_dir / "report.md", report)`｜磁盘写 OSError 将替换本应成功返回的 report（且此时 process 已交付 artifacts），错误码丢失｜建议包一层 try 或改为常规路径写
- 候选发现2：report.md 暴露内部 ID/偏移/错误码｜证据 pipeline.py:32 `- 错误代码：{code}`、:41 `[{char_start},{char_end})...模板 {template_id}`、:38-39 action_id/适用性英文状态｜用户报告含 char 偏移、action_id、模板 ID、原始错误码（联动 FL-D894）｜建议中文化/脱敏（报主线判定口径）
- 已知命中：无（DETAIL 中 pipeline.py 命中均为 guide_generation/pipeline.py）

### fundlex/v2_pipeline.py
- 结论：⚠️ 候选发现 2 条
- ① 与 pipeline.py 是评测 v2 演进关系（docstring 明说 v1 路径不动），evaluation/delivery 双模式流转自洽，review revoke 先于交付。② 失败一律 fail-closed 记例外清单，无伪造；但 exceptions 透出原始错误码。③ markdown 报告含内部哈希/passed= 英文化。④ 有冗余分支（见下）。⑤ `plan_v2` outcome 键（actions/edits/records/content_check）与 v2.py:1557 一致；`validate_edit_plan(..., {}, content_check=...)` 空模板 + content_check 组合符合 docx.py 契约；`release_runtime_context` 在 rules.py:57 存在。
- 候选发现1：review_blocked 重复兜底分支｜证据 v2_pipeline.py:270-271 与 :282-285 两处 `if review_blocked:` 做同一 update+return｜第一段属冗余死分支，第二段不可达前者已覆盖｜建议删一处
- 候选发现2：用户可见例外/报告透出内部码与哈希｜证据 v2_pipeline.py:60-62 `record_sha256=…[:16]…`、:69 `plan={plan_sha256}` `passed=`、:280-281 exceptions 直出 `failure_reason`（如 V3_ARTIFACT_SEMANTIC_REJECTED）｜交付模式例外清单面向用户却为机器码（联动 FL-D894）｜建议例外提供用户措辞 + code 附注（报主线判定）
- 已知命中：无

### fundlex/stage_replay.py
- 结论：✅ 无发现
- ① 离线只读重放，stage 白名单 + boundary 完整性（stage/inputs_sha256）双重校验，无状态机。② `_RecordedGateway` 缺 cassette 即 `MODEL_REPLAY_MISS`，never fall back to live 与 docstring 一致；证据不符 raise FrozenError，无吞错。③ 仅评估产物/错误码，非用户可见。④ 无 TODO；`fields(Target)` 过滤为有意兼容。⑤ `_facts`→`facts_from_value`（recall.py:1021）、`replay_claims`/`check_delete_residuals` 关键字参数与 claim_replay.py:1293/2503 逐一对齐；`git rev-parse` 为只读探测且无 git 时兜底 None。
- 已知命中：无

### fundlex/semantic_contract.py
- 结论：⚠️ 候选发现 2 条
- ① opt-in 纵向切片（FUNDLEX_SEMANTIC_V2），业务适用权留调用方，职责清晰。② `validate_semantic_target` 全检查返回 (False, reason) 不吞错；但 context 构建有静默 continue。③ 无用户可见输出（提示词面向模型）。④ 无 TODO；说明行 191-195 解释旧死分支移除合理。⑤ `parse_semantic_targets`/`discover_for_rules` 与 recall_pipeline.py:5030-5038 调用签名、facts 传参一致；`semantic_target_to_target` 字段与 recall.py:1700 Target 一致；operation 归属 fallback 有一致性约束（恰一匹配才采纳）。
- 候选发现1：构建模型上下文静默丢弃异常 location｜证据 semantic_contract.py:152-155 `except Exception: continue`｜某 section 的 by_location 失败时模型收不到该段，可能漏报目标且无任何 rejected 记录（无追溯）｜建议记入 rejected 并附 reason:context_load_failed
- 候选发现2：未知 rule_id 静默跳过｜证据 semantic_contract.py:363-366 `if policy is None or rule is None: continue`｜env 配置的语义规则名写错时无任何信号，语义发现静默无产出｜建议记录 rejected {rule_id, reason:"policy_or_rule_missing"}
- 已知命中：FL-D552（A8-F1，_ENGINE_BUILD_MODULES 漏挂本文件，已修复 a8d78f2）

批次小结：6 文件共 7 条候选发现。最严重为 pipeline.py:222 finally 块写报告失败可掩盖成功结果；其次是 semantic_contract.py 两处静默跳过（context 加载失败、未知规则）与本项目 fail-closed 纪律相悖；v2_pipeline 冗余分支与用户可见例外透出机器码为低危可读性/整洁问题。registry/stage_replay 干净；跨模块调用签名与字段假设 5 处抽查全部匹配，未发现职责矛盾。
