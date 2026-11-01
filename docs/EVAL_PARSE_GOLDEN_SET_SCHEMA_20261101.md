# A2 解析黄金集 Schema（v1，2026-11-01，qa-feat-recall EVAL 轨）

> 目标：为「指引解析 → 规则产物」建立独立金标准，支撑 A3 三层指标（规则召回率/结构正确率/直接可用率）。
> **纪律同合同标签**：标签先行、冻结先行（sha 链入 freeze.json）、schema 本文档化；防循环铁律见 §6。

## 1. 双层结构

```
parse-golden-v1/
├── manifest.json            # 全集清单：guide 条目 × 标签件 sha × 形态族 × 轨道
├── freeze.json              # 冻结记录（labels sha 链、构建代码 commit、冻结时刻、来源核验）
├── guides/<guide_id>/
│   ├── source.docx|pdf      # 指引原件（冻结件，sha 见 manifest）
│   ├── text-extract.json    # 确定性文本抽取留痕（段落+表格，工具版本入 freeze）
│   ├── rules-gold.json      # G 层：规则级金标签（盲读人工标注）
│   └── outcomes-gold.json   # O 层：结果级金标签（配对合同确定性推导，仅 fee-rule-v2 种子有）
└── checks/
    └── verify_labels.py 输出留痕
```

## 2. G 层 schema（rules-gold.json）——规则召回率/结构正确率的分母

```json
{
  "schema": "fundlex-parse-gold-rules-v1",
  "guide_id": "fee-rule-v2",
  "guide_sha256": "<原件 sha>",
  "morphology_family": ["条文型", "附条件适用", "定义引用", "勘误型"],
  "track": "A(gold-full)",
  "rules": [
    {
      "rule_key": "R05",
      "source_heading": "基金份额的申购与赎回-六、申购和赎回的价格、费用及其用途",
      "source_paragraph_span": [60, 63],
      "op": "replace | delete | append | conditional_group",
      "intent_zh": "赎回费用归入基金财产口径全额化的三种旧表述统一",
      "applicability": {"class_count": "single|multiple|any", "requires_service_fee": true,
                        "product_feature": "floating_mgmt_fee|null"},
      "old_variants": [{"text_sha256": "…", "text_preview": "前40字…"}],
      "new_text_sha256": "…",
      "group_link": ["R05 与 R06 同属一组条件替换"],
      "notes": "labeler 备注（边界、歧义声明）"
    }
  ],
  "labeler": {"method": "blind-read-2pass", "tooling_commit": "<commit>", "model_assist": "none|extract-only"},
  "frozen_at": "…", "labels_sha256": "…"
}
```

- `op` 枚举与引擎操作面同义（replace/delete/append），指引特有形态用 `conditional_group`（条件分组替换）。
- 文本一律 sha+预览双件：评分按 sha 精确/容差两档，预览仅人检。
- `source_paragraph_span` 锚定 text-extract.json 的段落序号，供结构正确率的「来源结构对齐」判定。

## 3. O 层 schema（outcomes-gold.json）——直接可用率的分母

```json
{
  "schema": "fundlex-parse-gold-outcomes-v1",
  "guide_id": "fee-rule-v2",
  "pair_id": "fee-v2-05",
  "original_sha256": "…", "product_revised_sha256": "…",
  "derived_by": "deterministic-diff-v1（compare_docx，工具 commit）",
  "edits": [
    {"edit_key": "E03", "region_heading": "释义-基金份额类别定义", "op": "append",
     "old_text_sha256": "…|null", "new_text_sha256": "…", "rule_link": "R01|uncovered"}
  ],
  "boundary": {"uncovered_edits": ["产品侧改错/超出指引：如实保留并标明"], "notes": "…"}
}
```

- **确定性推导**：original→product_revised 的 diff 由 compare_docx 工具链机械产出，不经模型、不经人工改写；推导脚本与版本入 freeze。
- `rule_link=uncovered` 的产品侧改动保留在册（如实标注「超出指引的修改」），评分时单列，不塞进规则召回分母也不删除。

## 4. manifest 条目与形态族

- 种子：`fee-rule-v2`（指引 V2 原件 + v4 + v4_勘误版 三份同源指引做「版本族」）+ 33 配对 O 层。
- 扩充（按 GG 形态清单，待 GG A1《GUIDE_MORPHOLOGY》定稿对齐命名）：表格型/条文型/混合型/多级编号/脚注规则/勘误型/附条件适用/定义引用 8 族；每族 ≥1 真实或构造指引，构造指引须标 `synthetic:true` 且不与真实指引混算分母。
- B3 冷启动留出指引**不入**本集（独立冻结，防污染）。

## 5. A3 指标⇄本 schema 绑定

| 指标 | 定义 | 分母/分子来源 |
| --- | --- | --- |
| 规则召回率 | 解析产物规则命中 G 层 rule_key 的比例（含 variant 级命中判定） | G 层 rules |
| 结构正确率 | 命中规则的 op/applicability/来源标题/branch 结构四元错位率 | G 层命中项 |
| 直接可用率 | 解析产物不经人工修改驱动修订后，产出编辑覆盖 O 层 edits 且 zero wrong 的合同占比 | O 层 pairs |

## 6. 防循环铁律

1. **G 层盲读**：标注只读 text-extract（指引原文段落），**禁止**参阅 `guides/builtin_guide_v1.json` 等任何开发期规则产物；标注工具链与 builtin 零数据通路（脚本断言）。
2. **O 层独立**：确定 diff 推导不含解析产物；`rule_link` 映射在标签冻结**后**由独立脚本回填候选、人工只确认不改文本。
3. 一旦发现 gold 被解析产物污染（任一向导），该 guide 全件作废重建并入册（报主线赐号）。
4. gold 不为追求通过率而修改；评分失败是解析/引擎的失败，不是 gold 的失败（10-29 口径）。

## 7. 在制分层与冻结节奏

| 片 | 内容 | 冻结物 |
| --- | --- | --- |
| 片1 | 本 schema + O 层推导器 + 33 对 outcomes-gold | manifest+freeze+33 outcomes（确定性，先行） |
| 片2 | V2 指引 G 层盲读双遍标注 + 校验器 | rules-gold + verify 输出 |
| 片3 | v4/v4勘误 G 层 + 版本族差异注记 | 同左 |
| 片4 | 形态扩充批（真实收集+构造分批） | 逐批冻结，不憋全量 |
