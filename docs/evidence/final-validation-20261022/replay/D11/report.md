# FundLex 召回优先处理报告

- 引擎：recall_first 0.1.0（schema 3）
- 执行模式：delivery
- 源文件 SHA-256：74920e09c398f086091ca2b522c5d3bb0ed574d8ccd8c6e00ecf416b508ba93a
- 指引文档 SHA-256：45dd77460f2ef93d29001c0833c220f89de99dafb19d32a8b73653b55f92c8d7
- 交付状态：incomplete
- 资格：eligible（fund_type=open_regular；引文核验=True）
- 事实：份额类别 3（A、C、D）；销售服务费类别：C；浮动管理费：否
- 目标计数：应改 23，已符合 6，不适用 21；计划修改 14
- 审计轮次：2；未决问题 1
- 查漏：块 4，发现 2，未解决 1，缺口 0
- 模型调用：27；估算费用：0

## 每规则处置

- G01：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 0/1；章节 ['S03', 'S25']
- G02：覆盖 targets_found；目标 3（应改 0 / 已符合 2 / 不适用 1）；审计完成 0/0；章节 ['S03', 'S25']
- G03：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S04', 'S25']
- G04：覆盖 targets_found；目标 3（应改 0 / 已符合 2 / 不适用 1）；审计完成 0/0；章节 ['S04', 'S25']
- G05：覆盖 targets_found；目标 5（应改 4 / 已符合 0 / 不适用 1）；审计完成 1/5；章节 ['S04', 'S25']
- G06：覆盖 targets_found；目标 2（应改 0 / 已符合 0 / 不适用 2）；审计完成 0/0；章节 ['S04', 'S25']
- G07：覆盖 targets_found；目标 2（应改 0 / 已符合 0 / 不适用 2）；审计完成 0/0；章节 ['S07', 'S25']
- G08：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S07', 'S25']
- G09：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S07', 'S25']
- G10：覆盖 targets_found；目标 2（应改 0 / 已符合 0 / 不适用 2）；审计完成 0/0；章节 ['S07', 'S25']
- G11：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S07', 'S25']
- G12：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S07', 'S25']
- G13：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S07', 'S25']
- G14：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S07', 'S25']
- G15：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S16', 'S25']
- G16：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 0/2；章节 ['S16', 'S25']
- G17：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S16', 'S25']
- G18：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S17', 'S25']
- G19：覆盖 targets_found；目标 2（应改 0 / 已符合 0 / 不适用 2）；审计完成 0/0；章节 ['S20', 'S26']
- G20：覆盖 targets_found；目标 2（应改 0 / 已符合 0 / 不适用 2）；审计完成 0/0；章节 ['S20', 'S26']
- G21：覆盖 targets_found；目标 2（应改 0 / 已符合 2 / 不适用 0）；审计完成 0/0；章节 ['S20', 'S26']
- G22：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S20', 'S26']

## 审计轮次

- 第 0 轮（full）：规则 13，结论 17，另报 0，丢弃 0，问题 1
- 第 1 轮（incremental）：规则 1，结论 1，另报 0，丢弃 0，问题 1

## 查漏轮次

- 第 0 轮：块 4，发现 2，丢弃 7
  - SW001：G01 p91 missing_new_text → pending
  - SW002：G05 p129 residual_old_text → resolved

## 业务提示（不影响交付状态）

- [CONTRACT_POSSIBLY_ERRONEOUS] G15 p772：原合同可能有误：支付时限与指引参照不同（合同 5个工作日；指引 10个工作日）
- [CONTRACT_POSSIBLY_ERRONEOUS] G15 p1247：原合同可能有误：支付时限与指引参照不同（合同 5个工作日；指引 10个工作日）

## 未完成清单

- [target] {"kind": "target", "rule_id": "G01", "target_id": "S03_S04_S07_S16_S17_S20#1:T001", "location": "p91", "reason": "RECALL_APPEND_CLAUSE_INCOMPLETE", "failure_class": "VERIFICATION"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G01", "target_id": "S03_S04_S07_S16_S17_S20#1:T001", "location": "p91", "verdict": "incomplete", "reason": "AFTER is identical to BEFORE; the required appended clause about direct-sales A-class fee waiver, direct-sales C-class sales-service-fee waiver, and other-agency C-class fee cessation after one year is absent.", "evidence_verified": true, "failure_class": "GENERATION", "affected_fact": "", "affected_obligation": "G01:0 append 直销机构申购A类不收取认购/申购费用、直销机构申购C类不收取销售服务费、其他销售机构申购C类持有超一年不再收取销售服务费"}
- [sweep] {"kind": "sweep", "finding_id": "SW001", "rule_id": "G01", "location": "p91", "source_location": "p91", "quote": "基金份额类别：本基金将基金份额分为 A 类、C 类和 D 类三种不同的类别。在投资者申购 A 类及 D 类基金份额时收取申购费用，不计提销售服务费；在投资者申购 C 类基金份额时不收取申购费用，而从本类别基金资产中计提销售服务费", "issue": "missing_new_text", "reason": "释义的基金份额类别定义条款后未增加关于直销机构申购A类（及D类）不收取认购/申购费用、直销机构申购C类不收取销售服务费、其他销售机构申购C类持续持有超过一年不再收取销售服务费的条款；该段在“计提销售服务费”处结束，缺少G01要求追加的新条款。", "artifact_start": 0, "artifact_end": 114, "chunk": "C001", "round": 0, "failure_class": "GENERATION", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G01", "operation_id": "G01:0", "obligation_id": "G01:B1:O1", "location": "p91", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G02", "operation_id": "G02:0", "obligation_id": "G02:B1:O1", "location": "p91", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G05", "operation_id": "G05:2", "obligation_id": "G05:B3:O1", "location": "", "code": "CLAIM_OPERATION_UNPROVEN", "reason": "verified site missing", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G16", "operation_id": "G16:0", "obligation_id": "G16:B1:O1", "location": "", "code": "CLAIM_OPERATION_UNPROVEN", "reason": "verified site missing", "failure_class": "TARGET"}

**交付状态：incomplete**
