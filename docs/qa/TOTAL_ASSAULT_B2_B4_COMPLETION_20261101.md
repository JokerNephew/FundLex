# 总攻完工报告（qa-recall-miss 线，2026-11-01）

> 范围：总攻令 ①B2 ②B4 ③B6 ④B5 ⑤B8 ⑥A5。验收口径 S2（fc=0 硬门/读实际产物/
> 机制面证明/如实留史）。双保险：A=本报告断言表+命令证据；B=双盲质检子 agent
> （PASS_WITH_NOTES，三条注全部修复后复检过）。

## 一、用户原话 → 断言表

| # | 用户原话（拆条） | 断言 | 证据 |
| --- | --- | --- | --- |
| 1 | B2：改字/删除/插入/替换/表格改值/条件适用/声明调整/跨条款联动 8 形态×合成用例 | ✅ 8 形态全覆盖合成案 13 例（含 S2b 隔离/S6 双分支/N1-N3 护栏） | docs/engine/RULE_FORM_MATRIX_20261101.md 矩阵表；/tmp/opencode/qa/form-matrix/matrix.json 13 键 |
| 2 | B2：×真实规则用例 | ✅ 真实规则 8 形态映射表（内置 22 规则 op 全画像+wave1-r2/BH 实证引用；表格形态真实分母缺口如实标出） | 同文档「真实规则侧证据映射」节 |
| 3 | B2：压当前引擎，形态×结果矩阵+失败归族 | ✅ 矩阵+三族归并（变体授权 B2-2/缺席证书 B2-3/孤件清理 B2-4）+ 已根治两项（B2-1/B2-5） | 矩阵文档汇总节+DETAIL_APPEND_B4_B2.md |
| 4 | B4：找绑定内置指引假设，列清单 | ✅ 17 项假设清单（4 高需裁决族+分档处置建议） | DETAIL_APPEND_B4_B2.md §B4-N1..N17 |
| 5 | B4：+消除记录 | ✅ 本批消除 2 项（B2-1 标题叶窄化 7a92027；B2-5 append 崩点 bb60222），各带病灶实证+mutation | 本表 #9 |
| 6 | B6：fc=0/wrong=0 在新形态下的护栏 | ✅ 全案 13/13 无 FALSE_COMPLETE/错改/编造；质量缺陷 2 格由读实际产物差分捕获并如实降级 | matrix.json honest 列；RULE_FORM_MATRIX 汇总 |
| 7 | B6：负例 mutation，进 CI 口径 | ✅ N1/N2/N3 真实负例+评分器 7 例单测入 CI（=`pytest tests/test_form_matrix_scorer.py` 7 passed） | tests/test_form_matrix_scorer.py |
| 8 | B5：38 FM 按语料罩面排歼灭序，出 v3 计划即可 | ✅ 6 序主攻+观测层+分波闸，量照 corpus_typology | docs/engine/FAILURE_ATLAS_V3_PLAN_20261101.md |
| 9 | B8：G14 天花板列观测项的观测设计 | ✅ 5 档判据+3 读数法+20% 立项阈值+既有锚点 | docs/qa/G14_OBSERVATION_DESIGN_20261101.md |
| 10 | A5：解析→引擎闭环，登记接口断点 | ⚠ 部分：接口断点台账 PB-1..PB-5 已登记；真机闭环**外部阻塞**（待 EVAL 黄金集），如实不冒称 | DETAIL_APPEND §A5 |
| 11 | 纪律：机制面修，禁止规则级/样本级特判 | ✅ 两处引擎修复均为机制级（QC 逐项核验无特判） | git show 7a92027/bb60222 + QC 报告 #2 |
| 12 | 纪律：每个修复带病灶实证+mutation 反例 | ✅ B2-1：S1 病灶+3 mutation；B2-5：抓栈+2 mutation+121 append 族绿 | 各 commit message+测试 |
| 13 | 纪律：真实模型不设上限，账本进状态文件 | ✅ ledger-form.sqlite / bh01-v4 25calls$0.0278 / bh07-v3 等入账 | /tmp/opencode/qa/status/qa-recall-miss.md |
| 14 | 质量双保险 A（原话断言+证据） | ✅ 本表 | 本表 |
| 15 | 质量双保险 B（双盲质检） | ✅ PASS_WITH_NOTES+三注全收（unchanged_ok/双向差分/输入快照），修复后矩阵重评；首检即捕获 B2-4 真实缺陷 | QC 会话 ses_e68a1d422ffehWfMCRRa2SxaPW；修复 commit b7a27f5 |

## 二、标的数字（如实留史）
- 引擎修复 2 项：B2-1（7a92027）、B2-5（bb60222）；penalty：B2-1 修复暴露于 S1 首跑，B2-5 暴露于 S3 2/3 崩。
- 矩阵：13 案真实模型跑（认证指引+发布方策略供给合法路径，前提已如实标注=[待批 B4-1]）。
- 回归：**2576 passed / 0 failed / 139 skipped**（含全部修复的终版全量回归，回执封板）。
- 待主线裁决：FL 号段 5 项（B2-1/B2-2/B2-3/B2-4/B2-5）+ B4-1 寄存闸设计裁决 + B4-N 分档裁定。

## 三、已知边界（不遮蔽）
1. 矩阵合法前提=发布方策略供给；工作台上传路径当前零执行（PB-1，需裁决）。
2. 表格改值真实分母空缺（r2 八案零 tbl 站点），第二波 corpus 补分层（已挂 B5 计划）。
3. S6a/S8 质量缺陷格是「产物有孤句/孤编号但引擎自闸判绿」——按严格口径记 honest=False，等 B2-4 治理后复评。
4. S3 历史性复跑：首次报错（not_generated honest）与其后修复版并排留史于 matrix 与文档修订记录。
