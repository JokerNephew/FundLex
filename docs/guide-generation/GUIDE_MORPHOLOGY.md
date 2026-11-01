# 指引形态库（GUIDE_MORPHOLOGY，2026-11-01）

> 总攻令 A1：压测样本即形态库。本清单登记「用户可能上传的真实指引形态族」，
> 每族给出：形态定义、构造样本（`tools/guide_shape_stress.py` 同源可复现）、
> 生产通道实测结果（`stress-report.json` 回填）、失败族登记链接。
> 结果列已按 parse-3 复验回填（数据：/tmp/opencode/qa/guide-stress/stress-report.json）。

## 形态族清单

| 族 | 形态定义 | 样本 | 实测结果 |
| --- | --- | --- | --- |
| 表格型 | 规则成行藏在 DOCX 对照表（位置/原表述/修订要求），正文仅引导 | T1_table_rows | ✅ certified（3 规则）·直驱 2 合同各 1/1 目标完成（费率替换规则未命中对应费率文本时 honest_hold，如实） |
| 条文型 | 通篇「第X条」编号，无任何领域标题与强调 | T2_article_only | ❌ parse failed：模型对「条文型」产出无旧文 replace，门 GUIDE_GROUP_INVALID 中文拦下（「该规则第 1 个操作的「替换」操作缺少原条款文本」），修复轮未收敛；失败族 FF-2 |
| 混合型 | 领域标题与条文编号混排（标题承规则、条文承操作） | T3_mixed | ✅ certified（3 规则）·直驱 2 合同各 1/1 目标完成 |
| 多级编号 | 一、（一）1. 三级文本编号嵌套承规则 | T4_multilevel_numbering | ✅ certified（3 规则）·直驱 2 合同各 1/1 目标完成 |
| 脚注规则 | 正文写「见脚注①」，**真实 OOXML footnotes.xml** 承载修订执行口径 | T5_footnote_rules | ✅→parse-3 机制修复后 certified（1 规则）·直驱定位目标 T3001（解析-3 前：failed，验证器中文诊断「脚注①的具体内容未包含在指南文本中」）；执行计划轮未生成义务→诚实扣件未伪装完成；失败族 FF-1 已修复+执行缺口登记 |
| 勘误型 | 单点更正「将A改为B」（费率/数字/名称订正） | T6_errata_ab | ✅ certified（1 规则）·直驱 0 目标（replace 空锚点 FL-D927 同族）；parse-3 前一轮曾 GUIDE_TEXT_NOT_VERBATIM 被拦（门正确），后模型改为逐字产出即过 |
| 附条件适用 | 「如果…则…否则…」分支执行口径（参照内置指引择一形） | T7_conditional | ⚠️ parsed 但 needs_review：canary OP_UNREGISTERED=G01:1（generated 第二分支落内置注册表外位置）——执行一致性成立，admission 缝隙入册 FL-GGAPPLY-03；失败族 FF-5 |
| 定义引用 | 先给术语定义段，规则正文引用所定义术语 | T8_definition_ref | ✅ certified（2 规则）·直驱 2 合同共 5/5 目标完成，交付 complete（定义引用形态全链路最佳） |
| 负·空文档 | 可解析但零内容 | N1_empty | ✅ 正确拒收：parse_failed GUIDE_SOURCE_EMPTY；issues 透露稳定码，中文映射在引导规范/api_content（前端渲染归前端线） |
| 负·伪文件 | 字节非 DOCX | N2_corrupt | ✅ 正确拒收：上传 415 UNSUPPORTED_FILE，不入解析 |
| 负·语义垃圾 | 合法 DOCX 但内容完全不是指引（菜谱/纪事），验证人话诊断 | N3_garbage_semantic | ✅ 正确拒收+诊断修复已生效：parse_failed GUIDE_MODEL_FAILED:MODEL_SCHEMA_INVALID；A7 修复后 remedy 为双修因人话（「请确认上传文件确为修订指引…」）；失败族 FF-4 已修复 |

## 既有形态（棒1 已验，同源归档）

七形态已在「多形态真实指引解析实战验证」实跑（docs/GUIDE_PARSE_REAL_MATRIX_20261101.md）：
标准标题（S1 certified+实改）、表承载（S2 修复轮后 certified）、泛化编号（S3 certified，
section_hint 丢失→定位率下降已登记 FL-D927 关联）、勘误微指引（S4 certified 但 replace
空锚点入册 FL-D927）、零强调（S5 certified+实改）、空（S6 显式拒收）、损坏（S7 显式拒收）。

## 判定口径

- 「直接可用」=生产通道 certified（validation clean + canary 过 + checklist 过）且
  （总攻口径）引擎直驱交付态 complete 或匹配目标 ≥1。
- 失败族登记：按「上传拒收 / 解析结构化拦下 / 认证拦下 / 解析成功但不可用」四类归档，
  每族附版本 issues 原文（脱敏）与代表样本 hash。
