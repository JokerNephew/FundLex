# EN2 · B 类 14 件主线裁决表（2026-11-01）

- 依据：总攻开工令②。每条：改动点 / 行为差异 / 风险 / 建议。属行为或语义变更，主线批量裁决后由本线施工。
- A 类 18 件已直修完毕（0f1db9b 之后逐件 commit，详见完工报告）。

| # | 发现 | 改动点 | 行为差异 | 风险 | 建议 |
| --- | --- | --- | --- | --- | --- |
| B1 | FL-D921 claim_replay 审计PASS清障连带吞结构失败 | claim_replay.py:2343-2346 清障仅限效果类失败码，结构完整性码（CLAIM_OPERATION_SPAN_UNAUTHORIZED/OCCURRENCE_MISMATCH 等）永久留存 | 义务翻 PASS 后，同义务结构失败不再消失；边缘场景 verified 由真转假（更严） | 历史产物解释口径变化；可能有依赖宽松 verified 的既有测试需复核 | **修（优先）**：fail-closed 方向单一，需补「审计PASS+结构FAIL并存」回归测试 |
| B2 | FL-D922 review api_key_env 落空继承 primary 凭据并绕过跨端点防护 | models/config.py:135-145/253-258：api_key_env 解析为空时抛 RoleConfigError；explicit_key 判空改按「值非空」 | 该误配从静默继承变为启动期报错 | 若现网正靠此误配运行，启动即失败（但当前即等于把密钥发错端点，属故障） | **修（第一优先）**：凭据安全；dedupe 修复后跑一次配置启动自检 |
| B3 | FL-D923 canary 吞错 → CERTIFIED fail-open | guide_store.py:210-222/750-752：canary 异常时 qualification 落 NEEDS_REVIEW（或新增 CANARY_ERROR 三态）并记 issues_json | canary 崩溃的版本从「静默认证放行」改为「待复核」 | 认证通过率观测值变化（更保守）；若设计本意是 advisory 需留书 | **修**：三态新增 CANARY_ERROR 最清晰，联 FL-D648 防护语义一并裁决 |
| B4 | FL-D924a manifest 丢 rule_id → 前端"规则 Gxx"标签消失；FL-D924b 弃奇偶配对 | docx.py:1561-1564 manifest 并入 rule_id/section（或 html_view 按 edit_id 回查 plan）；html_view._pair_revisions 改依赖 manifest.revision_ids | 审阅 UI 规则标签恢复显示；外来修订含 overlay 产物配对由 manifest 驱动 | manifest 结构新增字段（线协议前向兼容） | **修 a；b 随 a 一并做**：用户可见回归，修法明确 |
| B5 | FL-D925 后端 8 处用户可见技术串外泄点 | 按「用户语+code 附注」重构：claim_replay reason、v2 failure_reason、v2_pipeline exceptions/哈希、pipeline report.md、upload_guard 英文 message+RULESET_RETIRED、guide_report 内嵌原文/code、orchestrator 异常原文、reconciliation reason 机器态 | 用户可见文案中文化/脱敏；机器码仅留高级详情维度 | 前端 app.js/测试锚依赖旧 message 的断言需同步（FL-D733 语义锚口径） | **修，分批**：upload_guard 第一批（用户直见）；reason 机器码翻译层归属（后端中文案 vs 前端映射）请主线先定口径 |
| B6 | FL-D926 pipeline finally 写报告失败掩盖结果 | pipeline.py:216-222：finally 内 _write_report_markdown 包 try/log 或移出 finally | 磁盘写失败不再替换成功返回 | 评测工具对报告缺失的容忍度需确认 | **修**：风险极低 |
| B7 | FL-D927 semantic_contract 两处静默跳过 | :152-155/:363-366 静默 continue 改记 rejected+reason | opt-in 语义发现从「无声漏」变「显式拒绝记录」 | 无（当前 opt-in） | **修**：方向 fail-closed 一致 |
| B8 | FL-D930 canary 谓词双镜像漂移 | guide_canary._declared_key 与 recall._declared_operation_key 抽共享实现或加谓词等价性测试 | 无运行时行为变化（治理） | 触碰 EN1 文件 recall.py，需协调署名 | **修（加测试先行）**：抽共享实现放第二步 |
| B9 | FL-D931 guide 解析指令残留 15-group 暗示 | guide.py:465-466 删句或挪内置专用上下文 | 新指引解析 prompt 不再被 15 组暗示；模型输出分组更贴源 | 内置指引解析结果可能微变（实测对照） | **修**：联 FL-D898 质量门，用真实新指引做前后 A/B 实测后再定删/挪 |
| B10 | FL-D932 coverage legacy 投影 satisfied 错标 | generation/coverage.py:440-444 satisfied→ALREADY_SATISFIED | 旧报告"已满足"不再被标不适用；两态均不阻断 | 旧评测基线计数变化 | **裁决：**改语义 vs 保留兼容——偏向改语义并注明 |
| B11 | FL-D933 router executor 重算无视 spec.executor | router.py:331-336 改读 spec.executor（或加一致断言） | 未来注册自定义 executor 立即生效（当前无不符项，零现状变化） | 若 registry 填错 executor 不再被 tier 兜底 | **修（断言版）**：先加一致断言，成本最低且 warn 即暴露 |
| B12 | FL-D934 flags registry_shadow 死模式 | 实现宣称的观测 telemetry 或删第三态 | 删态：env 配 shadow 回落 registry 默认；实现：新增影子路由日志 | 若生产有人配 shadow（查无记录）行为变 | **裁决：删态**（声明而未实现是半成品；观测需求可另立工单） |
| B13 | FL-D935(3)(7) obligations.project / variants.authorized_variant_sentences 死形参 | 删 rules_by_id/artifact_text/rule 形参+同步调用面（recall_pipeline 2 处、recall.py 1 处） | 无行为差异，接口收窄 | 触碰 EN1 文件（recall/recall_pipeline 调用点） | **修**：EN1 协同，一 commit 两侧同步 |
| B14 | FL-D936(3) ModelCassette._locks 无界增长 + FL-D937(1)(4)(5)(6)(8)(11)(12) 治理包 | 锁表改有界/用完清（或裁决接受）；release_gate 裸 ValueError 改 RuleError(code)（改测试断言）；v2 docstring 更正双轨；qualification 版本入 recall_prompts 注册表；user_agent 取包元数据（5 处）；FACT_BLOCKED_CODES 与 router 产出对齐（删条目或真发码）；artifact_review 键对齐 EVAL 工具（移交 EVAL 线）；obligations 动态 import 静态化 | 治理一致性；user_agent 字符串对外变（0.3.0→包版本） | release_gate taxonomy 改动需测试断言同步；user_agent 变更面外链观测 | **裁决各子项定性**：建议 11 移交 EVAL、8 选「真发码」、6 统一取 importlib.metadata |

## 施工衔接
- 裁决回流后，本线按同样纪律施工（逐件 commit+定向测试+回归），只不触碰裁决为「不修」项。
- B13/B8 涉 EN1 文件，请主线在任务单中注明协同。
