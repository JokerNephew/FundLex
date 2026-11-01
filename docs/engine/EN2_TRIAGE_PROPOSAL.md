# EN2 发现分级处置提案（2026-11-01，供主线批量派修）

- 范围：FL-D921~937 全部登记项（含合集子项逐条分级），证据详见 docs/DETAIL_APPEND_EN2.md。
- 分级口径：
  - **A 可安全直接修**：死代码/注释/文案/纯整洁，不改业务行为或仅收窄 ops 面（派修即可，修复批回归验证）。
  - **B 需主线裁决**：行为/状态/税语义变更，或触碰他线文件调用面。
  - **C 需用户裁决**：产品语义/对外呈现由用户拍板。
- 本线仅提案，不动业务代码。

## A 类 · 可安全直接修（18 项）

| 编号 | 修法一句话 |
| --- | --- |
| FL-D928 | effects.py:804/1058/1063 给 int(occurrence_index) 补 try 防护，失败走 UNPROVEN（对齐 coverage.py:249-252 同工程口径） |
| FL-D929（部分） | 删 reconciliation.py:242-244 不可达 MISS_REVIEW_PENDING 分支；为 MISS_COVERAGE_RESIDUAL 补与 EDIT_LOST 同款预留注释 |
| FL-D935(1) | 删 validators.py:569-577 死代码 `_token_context` |
| FL-D935(2) | 删 obligations.py:400-412 死代码 `_audit_verdicts`（活副本在 coverage.py:119） |
| FL-D935(4) | 删 recovery/orchestrator.py:195-196 孤儿 `failure_codes()` 或归入测试工具 |
| FL-D935(5) | 删 frozen.py:57-59 `_path()` 内未参与返回的局部 `identity` |
| FL-D935(6) | 删 regulatory/ingestion.py:62-64 死赋值（标题合并 mutate 后即被切片丢弃） |
| FL-D936(1) | policies.py:86 裸 int() 包 try，配错值抛 RecoveryPolicyError 并带 env 名（对齐 with_overrides 同文件口径） |
| FL-D936(2) | trace_sink.py 里 `_CAPTURE_TEXT` 只取一次快照或用线程本地，去掉 trace_document 内 global 改写 |
| FL-D936(4) | roles.py metrics() 对 event dict 先拷贝再注 role，绝不再地改 gateway 事件表 |
| FL-D936(5) | regulatory/pdf_parser.py:73 pymupdf 文档 try/finally close（或 contextlib.closing） |
| FL-D936(6) | 删 v2_pipeline.py:270-271 与 :282-285 重复 review_blocked 分支中的一段 |
| FL-D936(7) | selective.py:612-615 `_manifests_from_report(report)` 算一次存入局部变量后复用 |
| FL-D936(9) | claim_replay.py:2575 改 getattr 链防御（与 :1379 同文件同口径） |
| FL-D936(10) | docx.py:478-481/1028-1030 防御性 except 加注释说明拦底依据 |
| FL-D937(2) | rules.py:725 局部变量 `re` 改为 rstart/rend 类名，除遮蔽 stdlib |
| FL-D937(3) | rules_v2.py:190 注释拼写 `TEMPLATE_VARIANT_UNNAPROVED` → `TEMPLATE_VARIANT_UNAPPROVED` |
| FL-D937(9)+FL-D937(10) | components.py docstring 与 any() 语义对齐（“任一命中”）；template.py:431 的 -120 提为命名常量并记出处 |

## B 类 · 需主线裁决（14 项）

| 编号 | 修法一句话（供裁决定夺） |
| --- | --- |
| FL-D921 | claim_replay.py:2343-2346 清障仅限效果类失败码，结构完整性码（SPAN_UNAUTHORIZED/OCCURRENCE_MISMATCH 等）永久留存——改核验语义，须配回归测试 |
| FL-D922 | models/config.py：review api_key_env 解析为空时抛 RoleConfigError 而不得回落继承 primary 密钥（守卫 explicit_key 判定改按“值非空”）——凭据外发风险，建议优先 |
| FL-D923 | guide_store.py canary 异常时 qualification 落 NEEDS_REVIEW（或新增 CANARY_ERROR 三态）并把异常摘要记 issues_json |
| FL-D924 | a) docx.py manifest 写入并入 rule_id/section（或 html_view 投影按 edit_id 回查 plan）；b) _pair_revisions 改依赖 manifest.revision_ids，不再凭奇偶（外来修订契约） |
| FL-D925 | 后端 8 处外泄点按“用户语 + code 附注维度”统一重构，upload_guard 英文 message 第一批施工（需先定译层归属：后端中文案 vs 前端映射，主线定） |
| FL-D926 | pipeline.py finally 内 _write_report_markdown 包 try/log，或移出 finally 走常规路径写 |
| FL-D927 | semantic_contract.py 两处 continue 改记 rejected + reason（context_load_failed / policy_or_rule_missing） |
| FL-D930 | guide_canary `_declared_key` 与 recall `_declared_operation_key` 抽共享实现或加谓词等价性测试（触碰 EN1 文件 recall.py） |
| FL-D931 | guide.py 解析指令删/挪 “15-group” 句（留在内置指引专用上下文），联 FL-D898 质量门实测新指引解析 |
| FL-D932 | coverage.py legacy 投影 satisfied → ALREADY_SATISFIED（需裁决旧报告计数语义兼容口径） |
| FL-D933 | router.py:331-336 改读 spec.executor 或加“注册 executor 与 tier 推导一致”断言 |
| FL-D934 | flags.py registry_shadow：实现宣称的观测 telemetry 或删三态第三态（FL-D558 相邻项合并判） |
| FL-D935(3)、FL-D935(7) | obligations.project 删死形参（recall_pipeline 两调用面同步改）；variants.authorized_variant_sentences 删 rule 形参（recall.py:7149 调用面同步改） |
| FL-D936(3) | ModelCassette._locks 无界增长：主线裁定接受现状或改为有界/用完即清 |
| FL-D936(8) | guide.py _model_summary 快照失败记入 events/rounds_detail（是否进用户审计维度由主线定） |
| FL-D937(1)、FL-D937(4) | validate_release_gate 裸 ValueError 改 RuleError(code)（改 tests/test_rules_catalogue 断言）；v2.py docstring 更正为评测+交付双轨 |
| FL-D937(5)、FL-D937(6)、FL-D937(8)、FL-D937(11)、FL-D937(12) | qualification prompt/schema 并入 recall_prompts 注册表；user_agent 从包元数据取版本（5 处统一）；FACT_BLOCKED_CODES 里 FACT_NOT_VERIFIED 与 router 产出对齐（删条目或真发该码）；artifact_review v3 产物键与 development_gate_reconciliation 对齐（移交 EVAL 线）；obligations.py 动态 __import__ 改模块级静态导入（若无循环依赖证据） |

> B 类表中 FL-D935(3/7)、FL-D936(3/8)、FL-D937(1/4/5/6/8/11/12) 共 11 行打包列出，与 A 类无重叠。

## C 类 · 需用户裁决（1 项）

| 编号 | 修法一句话（供用户拍板） |
| --- | --- |
| FL-D937(7) | user_model_connections.py:20-35 PROVIDERS 内置模型清单：是否按供应商现行目录更新下拉可选项（用户决定列出哪些新模型；custom 通道已是兜底） |

## 顺序建议（供主线排批）

1. 第一批：B 类 FL-D922（凭据安全）→ FL-D921 / FL-D923 / FL-D924a（核验语义与交付面）；
2. 第二批：FL-D925 后端外泄点（配合已开工的 FL-D894 前端译层）；
3. 第三批：A 类 18 项打包一次修复批 + 定向回归；C 类随用户下一轮拍板。
