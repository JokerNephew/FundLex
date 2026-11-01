# EN2 引擎审计2线 · 逐文件审计报告（终版）

- 基底：a96f118（对齐 docs/COVERAGE_MATRIX_20261101.md 生成基底；本树 HEAD 由 158475f fast-forward 而来，矩阵为唯一派工依据）
- 审计维度：①职责与状态机 ②失败路径（静默吞错/兜底文案技术腔/失败被报成功）③用户可见输出可读性（联动 FL-D894 技术内容外泄）④死代码/TODO/半成品 ⑤跨模块一致性假设
- 方式：11 个批次子审计员逐行全读（无双重重叠，回报原文收 docs/engine/en2_batches/B1~B10+B6a+B6b 共 11 档），主审对全部高危/中危候选证据点亲自逐行复核（25+ 处）后方入册
- 发现编号：FL-D921~937 收册于 docs/DETAIL_APPEND_EN2.md（FL-D938/939 预留未用）
- 覆盖：64/64 文件，100%，无抽样、无遗漏
- 矩阵签认说明：按「多 agent 不并行改集中文档」纪律，本表为 EN2 名下 64 项的唯一签认载体，矩阵本体 ☐→✅ 由主线统一合并回填

## 一、结论摘要

- 整体工程质量高：主链路（docx/v2/generation/claim_replay/delivery）fail-closed 设计一致，未发现新的「修改失败报成功」通道；canary/smoke/reconciliation/recovery/trace 等全部确认为真实接线，非孤立脚本。
- 高危 4 项（报主线判定，建议优先）：FL-D921（审计 PASS 清障可连带吞结构失败）、FL-D922（review 凭据可能错发异端点且绕过防护）、FL-D923（canary 吞错→CERTIFIED 认证 fail-open）、FL-D924（html_view 修订清单 manifest 分支丢 rule_id 使用户「规则 Gxx」标签静默消失）。
- FL-D894 联动：FL-D925 给出后端侧 8 处技术串/内部码/原始异常外泄点，其中 upload_guard 英文 message 为用户直见（前端无映射），建议纳入 FL-D894 第一批施工。
- 中危 4 项：FL-D926/927/928/929/930/931/932/933（证据详附录）。
- 低危 3 合集：FL-D935 死代码 7 项、FL-D936 健壮性 10 项、FL-D937 治理一致性 12 项。
- 已知命中（不重复立案）：FL-D032/039/085/087/111/112/131/133/135/136/179-183/224/237/263/270/290/291/297/298/299/310/331/334/391/395/437/444/446/448/451/456/489/552/555/557/558/568/570/571/573/576/577/579/585/589/610/611/612/648/651/653/654/655/658/659/660/690/693/698/711/730/792/830/863 等（批次档内逐项标注，均无新恶化证据）。
- FL-D263（开放中）经批次核验根因位置与既登记录吻合、无恶化。

## 二、签认总表（64 项，✅=已全读属审，✅⚠=有发现）

| # | 文件 | 签认 | 发现编号 |
| --- | --- | --- | --- |
| 1 | fundlex/__init__.py | ✅ 无发现 | — |
| 2 | fundlex/application/__init__.py | ✅ 无发现 | — |
| 3 | fundlex/application/task_service.py | ✅ 无发现 | — |
| 4 | fundlex/artifact_review.py | ✅⚠ | FL-D937(11) |
| 5 | fundlex/checkpoints.py | ✅ 无发现 | — |
| 6 | fundlex/delivery.py | ✅ 无发现 | — |
| 7 | fundlex/docx.py | ✅⚠ | FL-D936(10) |
| 8 | fundlex/frozen.py | ✅⚠ | FL-D935(5)、FL-D936(3) |
| 9 | fundlex/generation/__init__.py | ✅ 无发现 | — |
| 10 | fundlex/generation/atomic.py | ✅ 无发现 | — |
| 11 | fundlex/generation/claim_replay.py | ✅⚠ | FL-D921、FL-D925(1)、FL-D936(9) |
| 12 | fundlex/generation/components.py | ✅⚠ | FL-D937(9) |
| 13 | fundlex/generation/coverage.py | ✅⚠ | FL-D932 |
| 14 | fundlex/generation/effects.py | ✅⚠ | FL-D928 |
| 15 | fundlex/generation/flags.py | ✅⚠ | FL-D934 |
| 16 | fundlex/generation/joint.py | ✅ 无发现 | — |
| 17 | fundlex/generation/registry.py | ✅ 无发现 | — |
| 18 | fundlex/generation/router.py | ✅⚠ | FL-D933 |
| 19 | fundlex/generation/template.py | ✅⚠ | FL-D937(10) |
| 20 | fundlex/generation/types.py | ✅ 无发现 | — |
| 21 | fundlex/generation/validators.py | ✅⚠ | FL-D935(1)、FL-D937(8) |
| 22 | fundlex/guide.py | ✅⚠ | FL-D931、FL-D936(8) |
| 23 | fundlex/guide_canary.py | ✅⚠ | FL-D930 |
| 24 | fundlex/guide_diff.py | ✅ 无发现 | — |
| 25 | fundlex/guide_report.py | ✅⚠ | FL-D925(6) |
| 26 | fundlex/guide_smoke.py | ✅ 无发现 | — |
| 27 | fundlex/guide_store.py | ✅⚠ | FL-D923 |
| 28 | fundlex/guide_text_diff.py | ✅ 无发现 | — |
| 29 | fundlex/html_view.py | ✅⚠ | FL-D924 |
| 30 | fundlex/models/__init__.py | ✅ 无发现 | — |
| 31 | fundlex/models/config.py | ✅⚠ | FL-D922、FL-D937(6) |
| 32 | fundlex/models/roles.py | ✅⚠ | FL-D936(4) |
| 33 | fundlex/obligations.py | ✅⚠ | FL-D935(2,3)、FL-D937(12) |
| 34 | fundlex/observability.py | ✅ 无发现 | — |
| 35 | fundlex/pipeline.py | ✅⚠ | FL-D925(4)、FL-D926 |
| 36 | fundlex/proxy_headers.py | ✅ 无发现 | — |
| 37 | fundlex/qualification.py | ✅⚠ | FL-D937(5) |
| 38 | fundlex/qualification_evidence.py | ✅ 无发现 | — |
| 39 | fundlex/recall_prompts.py | ✅ 无发现 | — |
| 40 | fundlex/reconciliation.py | ✅⚠ | FL-D925(8)、FL-D929 |
| 41 | fundlex/recovery/__init__.py | ✅ 无发现 | — |
| 42 | fundlex/recovery/history.py | ✅ 无发现 | — |
| 43 | fundlex/recovery/orchestrator.py | ✅⚠ | FL-D925(7)、FL-D935(4) |
| 44 | fundlex/recovery/policies.py | ✅⚠ | FL-D936(1) |
| 45 | fundlex/recovery/types.py | ✅ 无发现 | — |
| 46 | fundlex/regulatory/__init__.py | ✅ 无发现 | — |
| 47 | fundlex/regulatory/anchors.py | ✅ 无发现 | — |
| 48 | fundlex/regulatory/docx_parser.py | ✅ 无发现 | — |
| 49 | fundlex/regulatory/ingestion.py | ✅⚠ | FL-D935(6) |
| 50 | fundlex/regulatory/pdf_parser.py | ✅⚠ | FL-D936(5) |
| 51 | fundlex/retention.py | ✅ 无发现 | — |
| 52 | fundlex/rules.py | ✅⚠ | FL-D937(1,2) |
| 53 | fundlex/rules_v2.py | ✅⚠ | FL-D937(3) |
| 54 | fundlex/selective.py | ✅⚠ | FL-D936(7) |
| 55 | fundlex/semantic_contract.py | ✅⚠ | FL-D927 |
| 56 | fundlex/stage_replay.py | ✅ 无发现 | — |
| 57 | fundlex/trace_sink.py | ✅⚠ | FL-D936(2) |
| 58 | fundlex/upload_guard.py | ✅⚠ | FL-D925(5) |
| 59 | fundlex/upload_validation.py | ✅ 无发现 | — |
| 60 | fundlex/user_model_connections.py | ✅⚠ | FL-D937(7) |
| 61 | fundlex/v2.py | ✅⚠ | FL-D925(2)、FL-D937(4) |
| 62 | fundlex/v2_pipeline.py | ✅⚠ | FL-D925(3)、FL-D936(6) |
| 63 | fundlex/variants.py | ✅⚠ | FL-D935(7) |
| 64 | fundlex/workspace.py | ✅ 无发现 | — |

## 三、发现汇总（FL-D921~937）

| 编号 | 标题（详见 DETAIL_APPEND_EN2.md） | 级 | 状态 |
| --- | --- | --- | --- |
| FL-D921 | claim_replay 审计 PASS 清障连带清除同义务结构完整性失败 | 严重 | 报主线判定 |
| FL-D922 | review api_key_env 未置值静默继承 primary 凭据并绕过跨端点防护 | 严重 | 报主线判定（优先） |
| FL-D923 | guide_store 金丝雀吞错 → CERTIFIED 认证 fail-open | 严重 | 报主线判定 |
| FL-D924 | html_view 修订清单 manifest 丢 rule_id/（外来修订奇偶契约冲突） | 高 | a 修法明确 / b 报主线判定 |
| FL-D925 | FL-D894 联动：后端侧 8 处用户可见技术串外泄点 | 高 | FL-D894 联动报告 |
| FL-D926 | pipeline.py finally 写报告失败掩盖真实结果 | 中 | 建议修复 |
| FL-D927 | semantic_contract 两处静默跳过 | 中 | 报主线判定 |
| FL-D928 | effects.py occurrence_index 裸 int() 缺防抑 | 中 | 建议修复 |
| FL-D929 | reconciliation 不可达死分支 + CLASS_TEXT 僵尸类 | 中 | 报主线判定 |
| FL-D930 | guide_canary 准入谓词双镜像漂移风险 | 中 | 报主线判定 |
| FL-D931 | guide.py 解析指令残留“15-group”内置专属暗示（新指引质量门抵触） | 中 | 报主线判定（联 FL-D898） |
| FL-D932 | coverage.py legacy 投影 satisfied 错标 NOT_APPLICABLE | 低-中 | 报主线判定 |
| FL-D933 | router.py 按 tier 重算 executor 无视 spec.executor | 低-中 | 报主线判定 |
| FL-D934 | flags.py registry_shadow 无消费方（半成品 flag） | 低 | 报主线判定 |
| FL-D935 | 死代码合集×7 | 低 | 清理批次 |
| FL-D936 | 运行健壮性合集×10 | 低-中 | 修复批次（1/5/9 优先） |
| FL-D937 | 治理一致性合集×12 | 低 | 顺手批次（1/4/8 报主线判定） |
| FL-D938/939 | 预留未用 | — | — |

## 四、机制面与移交事项

1. **用户铁律落实**：64 文件 100% 全行审读，无抽样。批次回报原文（含 ①-⑤ 逐维结论与已知命中清单）收 docs/engine/en2_batches/，供主线复查与集中文档合并。
2. **不属于本线擅自处置范围**：修复、改造与 taxonomy 调整均报主线判定（愈合口径防「规则级补丁」反弹）。
3. **他线溢出**：`recall_pipeline.py:32` 死导入（strategy_mode，EN1 文件）已标注交 EN1；html_view 前端消费面（app.js:954）归前端主线；工具面 development_gate_reconciliation 归 EVAL。
4. **FL-D894 主体入册**：批次发现主文档尚未补登 FL-D894 本体（USER_REQUIREMENTS_20261101_SESSION2.md:131 已立项），建议主线回填，本册 FL-D925 作后端侧证据。
5. **交付完整性主场**：用户投诉「该修改但修改失败」（FL-D897 归 recall-miss）在 EN2 范围未复现直接引擎侧证据；docx/selective/delivery 链路双向校验与 fail-closed 完备。

（完）
