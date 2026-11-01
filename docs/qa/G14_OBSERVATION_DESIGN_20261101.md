# G14 MISS_TARGET_RESOLUTION 第二波观测设计（总攻 B8，qa-recall-miss）

> 背景：FL-D982 已如实交代——G14:3/4/5 落 MISS_TARGET_RESOLUTION 属目标解析层、
> 模型面 2/4 波动，非 FL-D869 域。总攻令⑤要求把它列为第二波观测项，本文给
> 判据 + 读数方法。r3 后 FL-D869 并入，G14 复发不记 FL-D869 回摆（已定界）。

## 观测对象与分母
- 分子：`operation_coverage` 中 rule_id=G14 的 6 个 op（G14:0..G14:5）。
- 分母：第二波语料中 **G14 适用**的合同 = 多份额类别且申购费用承担表述为模板
  变体的合同（以 corpus_typology.json 的 class_count=multiple ∩ 混合型分层为准；
  逐案以 facts.share_class_structure=VERIFIED 且 G14 condition_status=TRUE 判定，
  不用先验名单代替）。

## 判据（每 op 一档，逐案落类）
| 档 | 判定 | 读数来源 |
| --- | --- | --- |
| ✅ 直接命中 | completion=ARTIFACT_VERIFIED 且 basis=claim_replay:EXPECTED_EFFECT_PRESENT | report.json → operation_coverage.entries |
| ✅ 语义通道 | basis=claim_replay:SEMANTIC_VERIFIED | 同上 |
| ✅ 变体词通道 | basis=artifact_evidence:alternative_wording_absent | 同上 |
| ✅ 不适用 | NOT_APPLICABLE（condition FALSE，合法） | 同上 |
| ❌ 目标解析失败 | basis 含 MISS_TARGET_RESOLUTION / CLAIM_OPERATION_UNPROVEN「verified site missing」且 recovery=MARK_UNRESOLVED | 同上 + unresolved + recovery.actions |

## 读数方法（每波运行后执行，产物入波报告）
1. 脚本汇总：逐合同 G14 per-op 档位表 → 分母内各档占比（工具可复用
   form_matrix 的 coverage 读取；第二波放量后脚本化收进 tools/evaluation）。
2. 三指标：
   - **目标解析失败率** = ❌档 op 数 / G14 适用 op 总数（阈值：**>20% 触发独立立项修**；≤20% 维持观测）。
   - **通道构成**：✅三通道占比变化（语义/变体通道占比上升 = 模型面标志，下降+直接命中上升 = 机制进步）。
   - **flap 率**：同案跨波（r2↔r3↔第二波）档位翻转率；flap 高且两态均合法 = 波动实锤，flap 收敛到 ❌ = 机制缺陷实锤。
3. 留史口径：各波读数并排（S2），不覆盖；波间引擎版本差异标注。
4. 若触发立项：病灶案固定复跑矩阵（同 FL-D981 流程：mutation+真实复验+回归），修复方向候选=目标解析层的措辞变体鲁棒化（禁止规则级特判）。

## 既有数据锚点（挂上，不冒充第二波读数）
- r2 留出（05c3ef1，BH07）：G14:3/4/5 ❌ 目标解析失败 ×3。
- bh07-v3（含 FL-D869，同合同）：✅ 语义×1 + 变体词×2，flap=3/3。
- 本线历史：该形态 2/4 波动（模型面），当前判「观测」依据即此。
