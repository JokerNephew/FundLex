# FundLex 召回优先处理报告

- 引擎：recall_first 0.1.0（schema 3）
- 执行模式：delivery
- 源文件 SHA-256：c02ae5a04ffbb1a8c63a7408fb3c69fab4f54cd60ff44575f42031ab00e1289b
- 指引文档 SHA-256：45dd77460f2ef93d29001c0833c220f89de99dafb19d32a8b73653b55f92c8d7
- 交付状态：incomplete
- 资格：eligible（fund_type=open_regular；引文核验=True）
- 事实：份额类别 2（A类、C类）；销售服务费类别：C类；浮动管理费：否
- 目标计数：应改 24，已符合 7，不适用 23；计划修改 16
- 审计轮次：2；未决问题 1
- 查漏：块 4，发现 1，未解决 1，缺口 0
- 模型调用：27；估算费用：0.02805224999999999

## 每规则处置

- G01：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 0/1；章节 ['S03', 'S25']
- G02：覆盖 targets_found；目标 3（应改 0 / 已符合 2 / 不适用 1）；审计完成 0/0；章节 ['S03', 'S25']
- G03：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S04', 'S25']
- G04：覆盖 targets_found；目标 3（应改 0 / 已符合 2 / 不适用 1）；审计完成 0/0；章节 ['S04', 'S25']
- G05：覆盖 targets_found；目标 5（应改 3 / 已符合 0 / 不适用 2）；审计完成 1/3；章节 ['S04', 'S25']
- G06：覆盖 targets_found；目标 2（应改 0 / 已符合 0 / 不适用 2）；审计完成 0/0；章节 ['S04', 'S25']
- G07：覆盖 targets_found；目标 2（应改 0 / 已符合 0 / 不适用 2）；审计完成 0/0；章节 ['S07', 'S25']
- G08：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S07', 'S25']
- G09：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S07', 'S25']
- G10：覆盖 targets_found；目标 2（应改 0 / 已符合 0 / 不适用 2）；审计完成 0/0；章节 ['S07', 'S25']
- G11：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 2/2；章节 ['S07', 'S25']
- G12：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S07', 'S25']
- G13：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S07', 'S25']
- G14：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 1/1；章节 ['S07', 'S25']
- G15：覆盖 targets_found；目标 2（应改 1 / 已符合 0 / 不适用 1）；审计完成 2/2；章节 ['S16', 'S25']
- G16：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 0/2；章节 ['S16', 'S25']
- G17：覆盖 targets_found；目标 4（应改 4 / 已符合 0 / 不适用 0）；审计完成 4/4；章节 ['S16', 'S25']
- G18：覆盖 targets_found；目标 2（应改 2 / 已符合 0 / 不适用 0）；审计完成 2/2；章节 ['S17', 'S25']
- G19：覆盖 targets_found；目标 1（应改 0 / 已符合 0 / 不适用 1）；审计完成 0/0；章节 ['S20', 'S26']
- G20：覆盖 targets_found；目标 1（应改 0 / 已符合 0 / 不适用 1）；审计完成 0/0；章节 ['S20', 'S26']
- G21：覆盖 targets_found；目标 1（应改 0 / 已符合 0 / 不适用 1）；审计完成 0/0；章节 ['S20', 'S26']
- G22：覆盖 targets_found；目标 3（应改 2 / 已符合 0 / 不适用 1）；审计完成 2/2；章节 ['S20', 'S26']

## 审计轮次

- 第 0 轮（full）：规则 13，结论 20，另报 0，丢弃 0，问题 1
- 第 1 轮（incremental）：规则 1，结论 1，另报 0，丢弃 0，问题 1

## 查漏轮次

- 第 0 轮：块 4，发现 1，丢弃 9
  - SW001：G01 p93 missing_new_text → pending

## 业务提示（不影响交付状态）

- [CONTRACT_POSSIBLY_ERRONEOUS] G15 p1287：原合同可能有误：支付时限与指引参照不同（合同 5个工作日；指引 10个工作日）；支付路径/方式出现“自动支付/扣划”（指引参照未涉及）；支付路径/方式出现“指定账户路径”（指引参照未涉及）；支付路径/方式出现“无需出具指令”（指引参照未涉及）
- [CONTRACT_POSSIBLY_ERRONEOUS] G15 p821：原合同可能有误：支付时限与指引参照不同（合同 5个工作日；指引 10个工作日）；支付路径/方式出现“自动支付/扣划”（指引参照未涉及）；支付路径/方式出现“指定账户路径”（指引参照未涉及）；支付路径/方式出现“无需出具指令”（指引参照未涉及）

## 未完成清单

- [target] {"kind": "target", "rule_id": "G01", "target_id": "S03_S04_S07_S16_S17_S20#1:T001", "location": "p93", "reason": "RECALL_APPEND_CLAUSE_INCOMPLETE", "failure_class": "VERIFICATION"}
- [audit] {"kind": "audit", "code": "AUDIT_NOT_COMPLETED", "rule_id": "G01", "target_id": "S03_S04_S07_S16_S17_S20#1:T001", "location": "p93", "verdict": "incomplete", "reason": "AFTER is identical to BEFORE; the required appended clause about direct-sales A-class fee waiver, direct-sales C-class sales-service-fee waiver, and other-agency C-class one-year waiver was not added.", "evidence_verified": true, "failure_class": "GENERATION", "affected_fact": "", "affected_obligation": "G01:0 append 直销机构申购A类不收认购/申购费、直销机构申购C类不收销售服务费、其他销售机构申购C类持有超一年不再收取销售服务费"}
- [sweep] {"kind": "sweep", "finding_id": "SW001", "rule_id": "G01", "location": "p93", "source_location": "p93", "quote": "基金份额类别：本基金将基金份额分为 A 类和 C 类不同的类别。在投资者认购、申购基金份额时收取认购、申购费用，不计提销售服务费的，称为 A 类基金份额；在投资者认购、申购基金份额时不收取认购、申购费用，而是从本类别基金资产中计提销售服务费的，称为 C 类基金份额", "issue": "missing_new_text", "reason": "释义的基金份额类别定义条款后未增加关于直销机构申购A类不收认购/申购费、直销机构申购C类不收销售服务费、其他销售机构申购C类持有超一年不再收取销售服务费的新条款。", "artifact_start": 0, "artifact_end": 132, "chunk": "C001", "round": 0, "failure_class": "GENERATION", "routing_status": "MAPPED_TARGET", "status": "pending", "proof_kind": "SEMANTIC_UNCERTAIN"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G01", "operation_id": "G01:0", "obligation_id": "G01:B1:O1", "location": "p93", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G02", "operation_id": "G02:0", "obligation_id": "G02:B1:O1", "location": "p1036", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G03", "operation_id": "G03:0", "obligation_id": "G03:B1:O1", "location": "p1036", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G04", "operation_id": "G04:0", "obligation_id": "G04:B1:O1", "location": "p1036", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G08", "operation_id": "G08:0", "obligation_id": "G08:B1:O1", "location": "p1036", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G09", "operation_id": "G09:0", "obligation_id": "G09:B1:O1", "location": "p1036", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G11", "operation_id": "G11:0", "obligation_id": "G11:B1:O1", "location": "p1036", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G12", "operation_id": "G12:0", "obligation_id": "G12:B1:O1", "location": "p1036", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G14", "operation_id": "G14:3", "obligation_id": "G14:B2:O1", "location": "p1036", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G14", "operation_id": "G14:4", "obligation_id": "G14:B2:O2", "location": "", "code": "CLAIM_OPERATION_UNPROVEN", "reason": "verified site missing", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G16", "operation_id": "G16:0", "obligation_id": "G16:B1:O1", "location": "", "code": "CLAIM_OPERATION_UNPROVEN", "reason": "verified site missing", "failure_class": "TARGET"}
- [claim_replay] {"kind": "claim_replay", "claim_replay_failed": true, "rule_id": "G22", "operation_id": "G22:0", "obligation_id": "G22:B1:O1", "location": "p1036", "code": "CLAIM_OPERATION_NOT_PLANNED", "reason": "operation effect is not proven at every verified site", "failure_class": "TARGET"}

**交付状态：incomplete**
