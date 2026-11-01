# 批次B3回报（validators.py / template.py / types.py / components.py / generation/__init__.py）

来源：子审计员 ses_e69bd3d4（后台批次，2026-11-01 回报）。原文收录，未改结论。

## 批次B3报告

### fundlex/generation/validators.py（577行，逐行读完）
- 结论：⚠️ 候选发现 2条
- ① V1/V2 硬校验器，纯文本无副作用，fail-closed 状态收敛（verdict 优先级 UNKNOWN>FAIL>PASS）正确，无异常。
- ② 无任何 try/except，无兜底文案；所有未知态走 UNKNOWN/SOFT 路由，不把失败伪造为成功，无异常。
- ③ Finding code 为英文内部码（LOST_PROTECTED_LITERAL 等），经 recall.py:7171 进入 RecallError 载荷；是否到达用户可见面取决于异常层，本文件内无直接用户文案。
- ④ `_token_context`（569-577行）为死辅助函数，全仓 grep 无任何调用点；无 TODO/FIXME 类标记。
- ⑤ 3处跨模块抽查：`validate_policy_components` 签名与 recall.py:7158 调用一致；`run_validation` 的 components/auth 参数与 claim_replay/joint 消费一致；但见候选2。
- 候选发现1：死代码 `_token_context`｜证据 fundlex/generation/validators.py:569 `def _token_context(...)` 全仓仅定义无调用｜影响：维护噪声，语义为"移除检查窗口"暗示曾有未落地设计｜建议：删除或登记其设计意图（报主线判定）
- 候选发现2：`FACT_BLOCKED_CODES` 含永不出现的 code｜证据 validators.py:57 含 `"FACT_NOT_VERIFIED"`，但 router.py:289 仅把它作为 `fallback_reason` 字符串前缀，从不作为 Finding.code 产出｜影响：verdict 判断该分支恒不命中，跨模块命名空间混用误导读者｜建议：移除该条目或让 router 真正产出该 Finding code（报主线判定）
- 已知命中：无（文档 4283/5069 行仅为部署范围描述，非 validators.py 问题条目）

### fundlex/generation/template.py（434行，逐行读完）
- 结论：⚠️ 候选发现 1条
- ① Tier-1 纯文本变换，失败一律返回 None 交由 splice/compose 级联，职责单一，无状态机异常。
- ② 无静默吞错；`ValueError("POLICY_OPERATION_MISMATCH")` 为有意 fail-closed；完备性闸门（G09/G18/G14 拒收半成品）设计到位，无异常。
- ③ 无用户可见输出；evidence 字典为内部记账（tier1_template 等），无异常。
- ④ `_G09_VARIANTS` 长 pair 遮蔽问题已删冗余项留注释（属已知 FL-D577，已解决）；无 TODO/FIXME。
- ⑤ 3处调用点核对：recall.py:6850 `plan_fee_item_removal(actual, allowed, canonical_tail, allowed_order)`、:6930 `plan_g18_splice(actual, g18_pairs)`、:6940 `plan_g09_splice(actual, pairs)` 签名均匹配；但见候选1。
- 候选发现1：魔法收缩阈值无依据注释｜证据 template.py:431 `len(_compact(replacement)) < len(_compact(before)) - 120`｜影响：120 字符的安全边界无出处，调参或指引变更时无判据｜建议：命名常量并注明推导依据
- 已知命中：FL-D577（`_G09_VARIANTS` 长 pair 被短 pair 遮蔽，已解决已验证）；文档 6899/6900/7330 行为已登记的 G08/G18 修复描述，无新问题

### fundlex/generation/types.py（181行，逐行读完）
- 结论：✅ 无发现
- ① 纯 dataclass/Enum 定义层，StrategySpec→OperationSpec 继承关系清晰，无异常。
- ② 无失败路径代码，无异常。
- ③ 无用户可见输出，无异常。
- ④ 无 TODO/死代码；`RouteDecision` 三个兼容别名属性（executor/blocked_facts/requested_executor）均有 docstring 说明用途，非死代码。
- ⑤ `FACT_STATUSES` 三态与 validators.fact_blocking 的状态判定一致；`PolicyComponents.fact_dependencies` 字段与 router.py 消费方式一致，`as_dict` 与 template.py:38 调用一致，无异常。
- 已知命中：无

### fundlex/generation/components.py（159行，逐行读完）
- 结论：⚠️ 候选发现 1条
- ① 组件注册表+解析器，unknown id 抛 ComponentConfigError fail-closed，无异常。
- ② 配置错误显式抛出不静默，无异常。
- ③ 无用户可见输出（错误消息含组件 id，属配置层），无异常。
- ④ 无 TODO；`has_component` 跨模块导入 validators 私有函数 `_compact`（153行）为轻微耦合。
- ⑤ 3处调用点（recall_pipeline.py:5617、stage_replay.py:154、joint.py:98 调 `claim_components_for_rules`）签名匹配；但见候选1（文档与代码矛盾）。
- 候选发现1：模块 docstring 与判定语义矛盾｜证据 components.py:2-3 "complete only when **all** of its terms occur" vs validators.py:478-480 `any(...)` 注释明言"terms是alternative wordings, not a conjunction"｜影响：误导组件注册表维护者按"全部命中"设计词条，实际宽松放行｜建议：改 docstring 与 check_components 语义对齐
- 已知命中：无（文档 4283 行仅顺带提及文件名）

### fundlex/generation/__init__.py（82行，逐行读完）
- 结论：✅ 无发现
- ① 纯 re-export 门面，无状态，无异常。
- ② 无失败路径，无异常。
- ③ 无用户可见输出，无异常。
- ④ "legacy" 字样为特性旗标模式说明，非死代码，无异常。
- ⑤ 全部 33 个导出符号逐一核对在 coverage/flags/components/registry/router/types/validators 中真实存在，`__all__` 与 import 完全对应，无异常。
- 已知命中：无（文档 4872 行仅为未提交改动范围描述，非问题条目）

---

批次小结：5 文件共 1433 行全部逐行读完。该包整体工程质量高：无 except 吞错、无伪造成功、fail-closed 一致、无直接用户可见文案（FL-D894 维度干净）。4 条候选发现均为低危：1 个死辅助函数、1 个永不命中的 code 集条目、1 个无注释魔法阈值、1 个 docstring 与 `any()` 判定语义矛盾（最值得修，会误导组件词条设计）。已知命中仅 FL-D577（已解决）。
