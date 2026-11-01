# 批次B6a回报（rules.py / rules_v2.py / obligations.py）

来源：子审计员 ses_e69bc7c7a（后台批次，2026-11-01 回报）。原文收录，未改结论。

## 批次B6a报告

### fundlex/rules.py（905行，全读）
- 结论：⚠️ 候选发现 2条
- ① 职责清晰：v1 规则目录加载/发布门禁 + 文档身份/基金类型/份额 Profile 确定性提取与候选评估；与 rules_v2 并存，非死代码（pipeline.py 用其 load_ruleset/evaluate_candidates，v2_pipeline 复用其 classify/release_runtime_context），属"共享分类函数 + 两代加载器"的稳定共存。② 失败路径规范：模型失败归因为 code（ModelError→`model_profile_failed`、candidate 判定时 record reason code），无静默吞错，不伪造成功。③ 仅输出内部机读 code（RuleError/reason code），无直接用户文案；不生成文件路径/哈希给用户，无异常。④ 无 TODO/FIXME；无死函数发现。⑤ 抽查 pipeline.py（13）、v2.py（21）、v2_pipeline.py（21）、tests 多处导入名均存在且签名匹配，无异常。
- 候选发现1：`_fragmented_phrase` 局部变量 `re` 遮蔽 stdlib re 模块｜证据 rules.py:725 `rs,re=right_positions[0],right_positions[...]`｜影响：当前循环作用域内不再用 re 故无害，但后续维护者在函数内调用 re 会立刻 NameError/行为错乱｜建议直接改名（如 `rs,re_`→`rstart,rend`），非机制面可在修复批次顺手处理。
- 候选发现2：`validate_release_gate` 抛裸 `ValueError`（英文句）而同类门禁用 `RuleError(code)`｜证据 rules.py:99-127 `raise ValueError("release approval missing")` 等约10处｜影响：发布门禁错误 taxonomy 不一致，上层无法按 code 统一归因，错误文本只能在日志/测试断言中出现｜建议统一为 RuleError code，改法影响 tests/test_rules_catalogue.py 断言，报主线判定。
- 已知命中：FL-D133（ obligations/applicability 架构条目，rules 相关分类仅部署列举，无冲突证据）。

### fundlex/rules_v2.py（268行，全读）
- 结论：⚠️ 候选发现 1条
- ① 职责明确：v2 可执行规则包 Loader + 发布证据校验；非半成品——被 v2_pipeline、v2.py、artifact_review、rules/release_v2.py 及至少4组测试实际使用；comment 明确定位为"Loader"。② 失败路径全 fail-closed：所有非法态抛带 code 的 RuleV2Error，JSON 解析异常包装为 V2_RULESET_INVALID，无静默。③ 无用户可见输出，纯机读。④ 无 TODO/deprecated；import 无冗余；发现一个注释拼写问题（见候选）。⑤ 抽查 `PROMPT_VERSIONS_V2`/`load_ruleset_v2`/`RuleV2Error`/`RuleSetV2` 全部调用点（v2_pipeline.py:22、release_v2.py:24、test_v2_release.py 等）签名匹配，无异常。
- 候选发现1：注释拼写错误引用不存在的 v1 常量｜证据 rules_v2.py:189-190 `(TEMPLATE_VARIANT_UNNAPROVED in v1)`，而 rules.py:655 实际为 `TEMPLATE_VARIANT_UNAPPROVED`｜影响：仅注释，易误导检索者按错误名 grep｜建议改注释拼写，琐碎。
- 已知命中：无。

### fundlex/obligations.py（691行，全读）
- 结论：⚠️ 候选发现 3条
- ① 职责符合 FL-D133 设计：Guide operation→Obligation IR 编译、tri-state 适用性挂载、claim-replay 证据投影、完成态不变量校验、OPEN_OBLIGATION 阻塞行投影；函数间状态机（PENDING→FOUND/MISSING→VERIFIED/UNPROVEN）自洽。② 失败路径强：编译期非法 guide 直接 raise；project 对冲突/阻塞证据显式置 UNRESOLVED 并记录 completion_evidence，无伪造成功、无宽松 except。③ 输出 internal code（OPEN_OBLIGATION/SCOPE_RULE_OMITTED 等 code + reason 字段），本层不产生自然语言用户文案，联动可读性收口在上层；本文件无异常。④ 见候选发现1（死代码）。⑤ 抽查 recall_pipeline.py:4833导入及调用（apply_facts/compile_obligations/project/project_unresolved）、stage_replay.py:79、guide.py:952 签名全部匹配；但发现2个形参全调用点都传、函数体从不用（候选2）。
- 候选发现1：`_audit_verdicts` 为死代码且与 coverage 重复定义｜证据 obligations.py:400-412；全仓 grep 仅函数自身引用，generation/coverage.py:119 有等价 `_iter_audit_verdicts` 被实际调用｜影响：维护两副本易漂移，读者误以为 Ledger 消费 audit verdict｜建议删除或标注，非机制面。
- 候选发现2：`project()` 形参 `rules_by_id`、`artifact_text` 函数体完全未引用，而 recall_pipeline.py:6433、6479 两处调用都传入实参｜证据 obligations.py:474/477（仅签名出现）｜影响：接口漂移，调用方以为 scope/target 判定依赖这些输入，实际被忽略，存在误导性的参数对象构造开销｜建议删参或注明保留理由，报主线判定（涉及调用面修改）。
- 候选发现3：`apply_facts` 用 `__import__("fundlex.applicability", ...)` 动态导入 resolve，而文件头部已静态 `from .applicability import ...` 同模块｜证据 obligations.py:23 vs 378｜影响：不一致写法掩盖依赖、绕开 import 检查工具；非功能缺陷｜建议改为模块级静态导入（若无循环依赖证据），报主线判定。
- 已知命中：FL-D133（本文件正题，架构设计与实现一致，无新恶化证据）。

批次小结：
- 3文件全部逐行读完；抽查定向测试 45 passed（test_obligations/test_rules_catalogue/test_v2_release）。
- 代码整体质量高：三路均 fail-closed、无静默吞错、无 TODO/半成品，rules_v2 非半成品且被实际使用，两代 loader 共存关系清晰。
- 6条候选全为低危：1处变量遮蔽、1处错误 taxonomy 不统一、1处注释拼写、1处死代码、1处死参数、1处死动态 import 不一致。
- 无用户可读性（FL-D894 联动）新发现：三本文件仅吐机读 code，文案收口在上层。
