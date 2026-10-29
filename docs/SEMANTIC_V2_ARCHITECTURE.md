# Semantic V2：模型语义 + 代码证明（2026-10-29）

## 目标
- 指引定义业务政策、适用条件和必须保留内容。
- 模型负责理解语义、找目标、识别变体、生成完整改写。
- 代码只负责真实 span、scope、授权范围、受保护内容和最终效果证明。
- 不再在 `recall.py` 里按合同句子逐份添加正则/变体。

## 当前落地（Phase 1，flag 开启）
- 新模块 `fundlex/semantic_contract.py`：`SemanticTarget`、`SemanticPolicy`、模型 schema/prompt、通用校验、Target 适配。
- 新策略文件 `guides/semantic_policies_v1.json`：G02/G03/G04/G05/G09/G18/G22 的 `policy_object`、`required_new_terms`、`preserve_terms`、selector 示例。
- 模型任务 `recall_semantic_target`：返回 `location / quote / operation_id / replacement / preserved_text / reason`。
- 代码校验：quote 逐字存在且唯一、location 在 scope、operation 属于规则、replacement 非空且变化、required_new_terms 存在、源段中出现的 preserve_terms 未被删除。
- 计划：`_plan_target_inner` 对带 `semantic_replacement` 的目标直接产生 `content_source=semantic_v2` 编辑；仍走 Claim Replay/Audit/Sweep。
- 开关：`FUNDLEX_SEMANTIC_V2=1`，`FUNDLEX_SEMANTIC_V2_RULES=G09,G22`（默认 G09,G22）。

## 明确边界
- 模型不决定 scope 和 artifact 事实；代码不决定合同措辞的语义。
- 失败回退：语义目标校验失败 → 记录 rejected，不产生编辑；不会自动改用旧正则补丁。
- 旧确定性分支暂时保留作 fallback/shadow；验证通过后再逐条移除。

## 待完成
1. 用真实合同验证 G09/G22 semantic v2，与旧分支影子对比。
2. 扩展到 G02/G04/G05/G18，删除对应合同特定分支。
3. 增加“失败证据回传模型重试”（丢失尾句/受保护词/摘要副本未改）。
4. 8 份 holdout 与扩样；只有影子评测不退化后才默认开启。
