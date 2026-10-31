# 第二波独立盲读标签 schema 与口径说明（labels-second-batch-20261031-v1）

冻结时间：2026-10-31。批次：`second-batch-20261031`（100 份；dev 75 / holdout 25）。

本文件说明第二波标签的 schema、生产口径与相对第一波（labels-first-batch-20261028-v2）的偏差。labels 文件与校验报告的冻结 sha 见 `/tmp/opencode/qa/status/labels-wave2.md` 与校验报告 envelope。

## 1. 生产链（冻结顺序）

1. 选样冻结：`docs/evidence/selection-second-batch-20261031.json`（seed=20261031，`tools/evaluation/select_second_batch_20261031.py` 可复现；与第一波 28 份 sha256 零重叠）。
2. 盲读标注：`tools/evaluation/first_batch_label_20261028.py`（第一波同一工具，未改）。
   - 主标 = 复核 = `qwen3.6-35b-a3b`（供应商分组内唯一承载约 80k token prompt 且返回合法 JSON 的非引擎模型；偏差登记 FL-D569）。
   - 引擎家族 kimi-k3 全程未参与任何标签决策；标注/收尾未读取任何引擎预测或产物。
   - 原始产物：`var/recall-first-evaluation/second-batch-20261031/labels-second-batch-20261031-v1.json`（sha256=`bc27df09…`，303 次调用，prompt 25.8M / completion 3.4M tokens，账本 `.usage.json`）。
3. 确定性收尾：`tools/evaluation/finalize_second_batch_labels_20261031.py` 对原始 v1 执行两遍（pass1 覆盖一致性补全 + pass2 逐段证据裁决），产出 `labels-second-batch-20261031-v1.final.json`；**最终受控副本**为 `docs/evidence/labels-second-batch-20261031-v1.json`，sha256=`423c6944687a6006d493d3f8dff4b4cb32593cc6acc26c2e2b3fb423622a88f5`。
4. 终检：`tools/evaluation/verify_second_batch_labels_20261031.py` → `docs/evidence/labels-second-batch-20261031-v1-verification.json`（problems=0；149 条启发式 warning 全部带 per-case 裁决记录；实测 warning=0 live）。

## 2. 顶层结构

与第一波 v2 相同：`schema`、`batch`、`source_root`、`selection`、`guide`、`labeler`、`cases[]`。`labeler.finalize` 记录收尾工具 sha、原始 labels 冻结 sha、变更明细与适用惯例清单。

## 3. case 字段

`case_id`、`group`、`file`、`relative`、`sha256`、`bytes`、`stratum`、`document`、`fund`（类别事实+证据段）、`rule_coverage[]`、`targets[]`、`satisfied[]`、`not_applicable[]`、`unknown[]`、`uncertain[]`、`label_quality`、`review`、`usage`、`finalize`。开发/留出划分由 `case_id` 前缀承载：`W2D*` = dev（75）、`W2H*` = holdout（25）。

- `rule_coverage[]`：`{rule_id, scope(main/summary), status(target|satisfied|not_applicable|unknown), paragraph_index, reason, evidence_quote}`。
- `targets[]`：`{target_id(T001..), rule_id, op, scope, paragraph_index, location, old_text, required_text, source_quote, anchor_quote, compact_start/end, old_text_sha256, paragraph_text_sha256, class_scope, rationale, requirement, confidence, review_flags, provenance, related_target_ids}`。
- `provenance`：`model`（盲读模型）或 `guide_deterministic_completion`（收尾构建）。二者均满足：old_text 必为原件实际文本切片；append 无 old_text。
- `label_quality.adjudicated_cleared`：逐条登记的裁决清单（`规则:段落` 或 `G01:释义`、`G16:scope`），与校验报告中被标记为 `adjudicated audit` 的启发式 warning 一一对应。
- `uncertain[]`：模型级疑点与收尾无法机械裁决事项的显式记录（31 条），不隐藏。

## 4. 收尾裁决口径（相对第一波的新增约定，均已在 finalize 内实现并逐案登记）

1. **一律按证据裁决，不造文本**：构建目标的 old_text 全部来自原件句子/片段；新文本仅来自冻结指引模板或指引规定的最小删改（如 G14 仅保留申购费率+销售服务费率、剔除赎回费率和转换费率——指引 G14 新文明确同时剔除两者）。
2. **跨段条款**（docx 把句号切到下一段）：拆为上下两片目标并用 `related_target_ids` 互链（G09/G13/G15/G18/G20 均有实例，如 W2D02 G11、W2D69 G13、W2D47 G18）。
3. **顺序清单清算条款** → `not_applicable`（沿用第一波 B15 裁决惯例，如 W2D30）。
4. **G05 站点必须在基本情况/摘要份额类别条款内**（沿用第一波 B05/B17 惯例；持有人大会、合同变更章节中的「调低赎回费率」不算站点，如 W2H20）。
5. **已改合同（partially-updated）**：证据命中新机制标志（返还给投资者 / 协商一致+指定账户路径 / 销售服务费（如有）/ 直销豁免句 / 直销版份额类别定义）→ `satisfied` 并附原文 `evidence_quote`。
6. **站点缺失**：经全文检索无站点（如合同本无 7 日惩罚句、摘要仅有费率和公式无支付安排、释义无份额类别定义段）→ `not_applicable`，原因写明。
7. **费率公式段不作 G15 删除目标**（G15 删旧支付安排，费率公式属保留文本）；托管费段落含「销售服务费」子标题字样不误伤。
8. **无销售服务费的多类别合同**（如 A1/A2/A3，W2D61）：G08/G11 模板条件不成立 → not_applicable；G14 新文本只保留申购费率（不强行注入销售服务费率）。这是对指引粗粒度 class_count 条件的事实优先解读，已登记 FL-D591。
9. **G02/G04**：类别定义已按收费组/字母联合表述 → satisfied（与第一波 G02/G04 状态分布一致：第一波 24/11 个 satisfied/NA、4/6 个 target）。
10. **G21 为 noop 规则**：所有 G21 unknown 归一为 not_applicable。
11. **保留 unknown（4 条，全部在 W2D65）**：原文表述与指引触发句存在实质差异的单一类别变体（G07/G10/G12/G14），无证据不做强行替换，理由保留；其 `uncertain` 记录含裁决建议。
12. **模型新文本修复**：极少数模型目标的新文本违反指引形态（G14 残留赎回/转换费率、G22 漏加销售服务费（如有）、多类缺销售服务费率），收尾器按其自身 old_text 确定性重写并打 `finalize_repaired_new_text` 标记。

## 5. 质量门

- verifier `problems=0`（coverage/target 双向一致、op 白名单、段落/哈希复核、保护文件无目标）。
- `label_quality.issue_count` 全 100 案为 0（第一波同口径）。
- 校验报告 149 条 warning 全部带 `adjudicated` 前缀并对应各案 `adjudicated_cleared`；无未裁决 live warning。
- targets 1254、coverage entries 4350、有目标案件 84/100、review=completed 100/100。
- 下游使用：本标签为第二波评测 gold；`references/fee-rule-v2/`（33 对产品部黄金对照）不混入本波分母，仅作后续扩波比对参照。
